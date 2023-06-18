import shutil
import subprocess
import sys
from os import environ
from pathlib import Path
from sys import stderr, platform
from typing import Dict, List


def fail(msg: str) -> None:
    """
    Print a failure message and an exit command, based on environment: 'exit' if
    in CI or 'return' if not.
    :param msg: Contextual message about the failure. Printed to stderr
    :return: None. Exits the script.
    """
    print(msg, file=stderr)
    if "CI" in environ:
        # We want to exit when in CI environment to fail the current shell
        print("exit 1")
    else:
        # Only return when run by a user so they don't lose their own shell
        print("return 1")
    exit(1)


def print_export_variables(export_env: Dict[str, str]) -> None:
    """
    Print commands to be executed by a shell to set up the environment
    :param export_env: mapping of environment variables to their respective value
    :return: None. Prints statements to be evaluated by a shell
    """
    for var, val in export_env.items():
        if platform == "win32":
            print(f"$env:{var} = '{val}'")
        else:
            print(f"export {var}='{val}'")


def main() -> None:
    # Variable and values to export
    export_env: Dict[str, str] = {}
    exe_suffix = ".exe" if platform == "win32" else ""
    script_suffix = ".bat" if platform == "win32" else ".sh"

    vcpkg_root = Path(environ.get("VCPKG_ROOT", ""))
    if "VCPKG_ROOT" not in environ:
        # GitHub Actions sets this
        if "VCPKG_INSTALLATION_ROOT" in environ:
            export_env["VCPKG_ROOT"] = environ.get("VCPKG_INSTALLATION_ROOT")
            vcpkg_root = Path(export_env["VCPKG_ROOT"])
        else:
            fail("Please set 'VCPKG_ROOT' environment variable to vcpkg root directory")

    vcpkg_exe = vcpkg_root / f"vcpkg{exe_suffix}"
    if not vcpkg_exe.exists():
        bootstrap = vcpkg_root / f"bootstrap-vcpkg{script_suffix}"
        if not bootstrap.exists():
            fail(f"VCPKG_ROOT ({vcpkg_root}) does not contain bootstrap script")
        subprocess.check_call([bootstrap], stdout=sys.stderr, cwd=vcpkg_root)

    nuget: List[str] = []
    if platform != "win32" and not shutil.which("mono"):
        fail("Please install 'mono' .NET framework runtime")
    elif platform != "win32":
        # Windows does not need mono
        nuget += ["mono"]

    nuget_exe = subprocess.check_output(
        [vcpkg_exe, "fetch", "nuget"], cwd=vcpkg_root, encoding="utf8"
    ).splitlines()[-1]
    nuget += [nuget_exe]

    nuget_user = environ.get("VCPKG_NUGET_USER")
    if not nuget_user:
        fail("Please set 'VCPKG_NUGET_USER' to your GitHub username")
    nuget_token = environ.get("VCPKG_NUGET_TOKEN")
    if not nuget_token:
        fail(
            "Please set 'VCPKG_NUGET_TOKEN' to your GitHub PAT with read/write package privileges"
        )

    export_env[
        "VCPKG_BINARY_SOURCES"
    ] = "clear;nuget,GitHub,readwrite;nugettimeout,3601"

    nuget_url = f"https://nuget.pkg.github.com/{nuget_user}/index.json"

    # fmt: off
    subprocess.run([*nuget, "sources", "add",
                    "-source", nuget_url,
                    "-storepasswordincleartext",
                    "-name", "GitHub",
                    "-username", nuget_user,
                    "-password", nuget_token],
                   stdout=sys.stderr, cwd=vcpkg_root)
    subprocess.check_call([*nuget, "sources", "update",
                           "-source", nuget_url,
                           "-storepasswordincleartext",
                           "-name", "GitHub",
                           "-username", nuget_user,
                           "-password", nuget_token],
                          stdout=sys.stderr, cwd=vcpkg_root)
    # fmt: on
    subprocess.check_call(
        [*nuget, "setapikey", nuget_token, "-source", nuget_url],
        stdout=sys.stderr,
        cwd=vcpkg_root,
    )

    # Check for primary token for readonly access to upstream sources
    primary_token = environ.get("VCPKG_PRIMARY_NUGET_TOKEN")
    if primary_token:
        primary_owner = environ.get("VCPKG_PRIMARY_NUGET_OWNER")
        if not primary_owner:
            fail(
                "Please specify 'VCPKG_PRIMARY_NUGET_OWNER' to the primary GitHub owner from which to download pre-built binaries"
            )

        if primary_owner == nuget_user:
            print(
                "Not using primary NuGet feed because it is same as 'GitHub' feed.",
                file=sys.stderr,
            )
        else:
            primary_url = f"https://nuget.pkg.github.com/{primary_owner}/index.json"
            # fmt: off
            subprocess.run([*nuget, "sources", "add",
                            "-source", primary_url,
                            "-storepasswordincleartext",
                            "-name", primary_owner,
                            "-username", nuget_user,
                            "-password", primary_token],
                           stdout=sys.stderr, cwd=vcpkg_root)
            subprocess.check_call([*nuget, "sources", "update",
                                   "-source", primary_url,
                                   "-storepasswordincleartext",
                                   "-name", primary_owner,
                                   "-username", nuget_user,
                                   "-password", primary_token],
                                  stdout=sys.stderr, cwd=vcpkg_root)
            # fmt: on
            export_env[
                "VCPKG_BINARY_SOURCES"
            ] = f"{export_env['VCPKG_BINARY_SOURCES']};nuget,{primary_owner},read"

    print_export_variables(export_env)


if __name__ == "__main__":
    main()
