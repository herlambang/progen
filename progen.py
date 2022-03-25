#!/usr/bin/env python
import argparse
import importlib
import logging
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s",
)

RESERVED_NAMES = (
    ".venv",
    "requirements.txt",
    ".git",
)

TEMPLATES = (
    ".coveragerc",
    ".env",
    ".flake8",
    ".gitlab-ci.yaml",
    ".isort.cfg",
    ".pre-commit-config.yaml",
    ".vscode/settings.json",
    "Dockerfile",
    "gitignore",
    "peru.yaml",
)

TEMPLATES_BASE_URL = (
    "https://raw.githubusercontent.com/herlambang/progen/main/templates"
)


def target_path(adir):
    path = get_target_path(adir)
    if path.is_dir():
        for f in path.iterdir():
            if f.name in RESERVED_NAMES:
                raise argparse.ArgumentTypeError(
                    f"Path is not empty and contains reserved files {RESERVED_NAMES}"
                )

    return adir


def get_target_path(adir):
    path = Path(adir)
    if not path.is_absolute():
        path = Path.cwd().joinpath(path)
    return path


def get_tmp_dir(path: Path):
    tmp_dir = path.joinpath("tmp")
    if not tmp_dir.is_dir():
        tmp_dir.mkdir()
    return tmp_dir


def get_template_dir(path: Path):
    template_dir = path.joinpath("templates")
    if not template_dir.is_dir():
        template_dir.mkdir()
    return template_dir


def get_poetry(cwd: Path):
    poetry_bin = get_poetry_bin()

    if not poetry_bin:
        tmp_dir = get_tmp_dir(cwd)
        get_poetry_py = tmp_dir.joinpath("getpoetry.py")
        url = "https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py"
        download_file(url, get_poetry_py)

        poe = importlib.import_module("tmp.getpoetry")
        base_url = poe.Installer.BASE_URL

        try:
            poe.urlopen(poe.Installer.REPOSITORY_URL)
        except poe.HTTPError as e:
            if e.code == 404:
                base_url = poe.FALLBACK_BASE_URL
            else:
                raise

        installer = poe.Installer(
            version=None,
            preview=False,
            force=False,
            modify_path=True,
            accept_all=True,
            file=None,
            base_url=base_url,
        )

        installed = installer.run()

        assert installed == 0


def get_poetry_bin():
    return shutil.which("poetry") or str(
        Path.home().joinpath(Path(".poetry/bin/poetry"))
    )


def exec_commands(commands):
    rc = 0

    for command in commands:

        if "cmd" in command:
            logging.info(command["cmd"])
            process = subprocess.Popen(
                command["cmd"],
                shell=True,
                stdout=subprocess.PIPE,
                cwd=command["cwd"],
            )

            while True:
                output = process.stdout.readline()

                rc = process.poll()

                if output:
                    print(output.decode("utf-8").strip())

                if rc is not None:
                    break

        elif "py" in command:
            logging.info(command["py"])
            try:
                command["py"]()
            except Exception as e:
                logging.error(e)
                rc = 1

        if rc and rc > 0:
            logging.error(f"None zero return code {rc}")
            break

    rc = 0 if rc is None else rc

    return rc


def download_file(url, file: Path):
    try:
        urllib.request.urlretrieve(url, file.absolute())
    except Exception as e:
        logging.error(e)
        logging.info(f"Cannot download {url}")
        return None
    else:
        logging.info(f"{url} downloaded as {file}")
        return file


def download_templates(path: Path):
    downloaded = []

    for tpl in TEMPLATES:
        tpl_url = os.path.join(TEMPLATES_BASE_URL, tpl)
        tpl_target = path.joinpath(tpl)

        if not tpl_target.exists():
            tpl_target.parent.mkdir(exist_ok=True, parents=True)

            if d := download_file(tpl_url, tpl_target):
                downloaded.append(d)
        else:
            downloaded.append(tpl_target)

    return downloaded


def quit(rc: int, tmp_dir):
    shutil.rmtree(tmp_dir)
    exit(rc)


def main():
    parser = argparse.ArgumentParser(
        prog="python progen.py",
    )
    parser.add_argument(
        "name",
        help="Project name",
        type=target_path,
    )

    args = parser.parse_args()

    cwd = Path.cwd()
    project_name = args.name
    project_path = get_target_path(project_name)
    tmp_dir = get_tmp_dir(cwd)
    template_dir = get_template_dir(tmp_dir)

    downloaded = download_templates(template_dir)

    if len(downloaded) < len(TEMPLATES):
        logging.error("Incomplete templates downloaded")
        quit(1, tmp_dir)

    try:
        get_poetry(cwd)
    except Exception as e:
        logging.error(e)
        logging.error("Unable to install poetry")
        quit(1, tmp_dir)

    poetry_bin = get_poetry_bin()

    commands = [
        {
            "cmd": f"{poetry_bin} new {project_name}",
            "cwd": cwd,
        },
        {
            "cmd": f"{poetry_bin} config virtualenvs.in-project true --local",
            "cwd": project_path,
        },
        {
            "cmd": f"{poetry_bin} config virtualenvs.create true --local",
            "cwd": project_path,
        },
        {
            "cmd": (
                f"{poetry_bin} add -D black isort flake8 flake8-docstrings "
                "flake8-annotations flake8-bugbear flake8-import-order flake8-builtins "
                "pep8-naming python-dotenv coverage pre-commit mypy pre-commit-hooks pytest-mock"
            ),
            "cwd": project_path,
        },
        {
            "cmd": f"{poetry_bin} install",
            "cwd": project_path,
        },
        {
            "cmd": (
                f"sed 's/{{project_name}}/{project_name}/g' "
                f"{template_dir}/.pre-commit-config.yaml > "
                f"{project_name}/.pre-commit-config.yaml"
            ),
            "cwd": cwd,
        },
        {
            "cmd": (
                f"sed 's/{{project_name}}/{project_name}/g' "
                f"{template_dir}/.flake8 > {project_name}/.flake8"
            ),
            "cwd": cwd,
        },
        {
            "cmd": (
                f"sed 's/{{project_name}}/{project_name}/g' "
                f"{template_dir}/.coveragerc > {project_name}/.coveragerc"
            ),
            "cwd": cwd,
        },
        {
            "cmd": (
                f"cp {template_dir}/.isort.cfg {template_dir}/.env "
                f"{template_dir}/.gitlab-ci.yaml {template_dir}/Dockerfile "
                f"{template_dir}/peru.yaml {project_name}; "
                f"cp {template_dir}/gitignore {project_name}/.gitignore"
            ),
            "cwd": cwd,
        },
        {
            "cmd": f"cp -r {template_dir}/.vscode {project_name}",
            "cwd": cwd,
        },
        {
            "cmd": f"git init",
            "cwd": project_path,
        },
        {
            "cmd": f"{project_path}/.venv/bin/pre-commit install",
            "cwd": project_path,
        },
    ]

    rc = exec_commands(commands)

    if rc < 1:
        happy = f"""
        
        Your project "{project_name}" is successfully set up!

        (*＾▽＾)/ Happy coding...
        
        """
        print(happy)

    quit(rc, tmp_dir)


if __name__ == "__main__":
    if sys.version_info < (3, 8):
        logging.error(f"Incompatible python version {sys.version} < 3.8")
        exit(1)
    main()
