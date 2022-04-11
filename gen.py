#!/usr/bin/env python
import argparse
import logging
import re
import shutil
import subprocess
import sys
import urllib.request
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s",
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
)

TEMPLATES_BASE_URL = (
    "https://raw.githubusercontent.com/herlambang/progen/main/templates/"
)

POETRY_URL = (
    "https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py"
)

DEV_DEPS = (
    "black isort flake8 flake8-docstrings flake8-annotations "
    "flake8-bugbear flake8-import-order flake8-builtins pep8-naming "
    "python-dotenv coverage pre-commit mypy pre-commit-hooks pytest-mock"
)

GIT_IGNORE = """/.vscode /.idea /.env /.venv /dist .DS_Store .pyc
*.ipynb* *.sqlite3 __pycache__ /tmp .pytest_cache .mypy_cache
.python-version"""


PERU = """
imports:
  k8s-deploy: k8s-deploy/

git module k8s-deploy:
  url: https://gitlab.com/wartek-id/infra/k8s-deploy.git
  rev: master

"""


def download_file(url, file: Path):
    logging.info(f"Downloading file {url}")
    urllib.request.urlretrieve(url, file.absolute())


class Generator(object):
    def __init__(
        self,
        name: str,
        path: Optional[Path] = None,
        force: bool = False,
    ) -> None:
        self.name = name
        self.force = force

        self.cwd = Path.cwd()
        self.base_path = path if path else self.cwd
        self.project_path = self.base_path.joinpath(self.name)

        self.tmp_path = self.base_path.joinpath(".tmp")
        self.template_path = self.tmp_path.joinpath("templates")

    @property
    def poetry_bin(self):
        bin = shutil.which("poetry")
        if not bin:
            bin = Path.home().joinpath(".poetry/bin/poetry")
            if not bin.exists():
                bin = None

        return bin

    def quit(self, return_code=0) -> None:
        if self.tmp_path.is_dir():
            shutil.rmtree(self.tmp_path)
        sys.exit(return_code)

    def init_project_path(self):
        if self.project_path.is_dir():
            not_empty = next(self.project_path.iterdir(), None)
            if not_empty and not self.force:
                raise Exception(f"{self.project_path} is not empty")

        self.tmp_path.mkdir(exist_ok=True)
        self.template_path.mkdir(exist_ok=True)

    def write_inline(self, name: str, content: str):
        self.project_path.joinpath(name).write_text(content)

    def download_templates(self):
        downloaded = []

        for tpl in TEMPLATES:
            tpl_url = TEMPLATES_BASE_URL + tpl
            tpl_target = self.template_path.joinpath(tpl)

            if tpl_target.exists():
                downloaded.append(tpl_target)
            else:
                tpl_target.parent.mkdir(exist_ok=True, parents=True)

                if d := download_file(tpl_url, tpl_target):
                    downloaded.append(d)

        return downloaded

    def get_poetry(self):
        return_code = 0

        if not self.poetry_bin:
            get_poetry_py = self.tmp_path.joinpath("getpoetry.py")

            download_file(POETRY_URL, get_poetry_py)

            poe = SourceFileLoader("poe", str(get_poetry_py)).load_module()
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

            return_code = installer.run()

        return return_code

    def shell(self, cmd: str, cwd: str, ignore_error: bool = False):
        logging.info(cmd)
        rc = 0
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            cwd=cwd,
        )
        while True:
            output = process.stdout.readline()
            rc = process.poll()
            if output:
                print(output.decode("utf-8").strip())
            if rc is not None:
                break

        if rc > 0 and not ignore_error:
            raise Exception("Shell error")

        return rc

    def copy_templates(self):
        for tpl in self.template_path.iterdir():
            logging.info(f"Copy {tpl} to {self.project_path}")
            if tpl.is_file():
                tpl.write_text(tpl.read_text().format(project_name=self.name))
                shutil.copy(tpl, self.project_path)
            elif tpl.is_dir():
                shutil.copytree(
                    tpl, self.project_path.joinpath(tpl.name), dirs_exist_ok=True
                )

    def run(self):
        self.init_project_path()
        self.get_poetry()
        self.shell(
            f"{self.poetry_bin} new {self.name}",
            self.base_path,
            ignore_error=self.force,
        )
        self.shell(
            f"{self.poetry_bin} config virtualenvs.in-project true --local",
            self.project_path,
        )
        self.shell(
            f"{self.poetry_bin} config virtualenvs.create true --local",
            self.project_path,
        )
        self.shell(
            f"{self.poetry_bin} add -D {DEV_DEPS}",
            self.project_path,
        )
        self.shell(
            f"{self.poetry_bin} install",
            self.project_path,
        )
        self.download_templates()
        self.write_inline(".gitignore", re.sub(r"\s+", "\n", GIT_IGNORE))
        self.write_inline("peru.yaml", PERU)
        self.copy_templates()
        self.shell(
            "git init",
            self.project_path,
        )
        self.shell(
            ".venv/bin/pre-commit install",
            self.project_path,
        )


def main():
    parser = argparse.ArgumentParser(
        prog="python gen.py",
    )
    parser.add_argument(
        "name",
        help="Project name",
    )
    parser.add_argument(
        "--path",
        type=Path,
        help="Project path",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force generate project",
    )

    args = parser.parse_args()

    gen = Generator(args.name, path=args.path, force=args.force)

    try:
        gen.run()
    except Exception as e:
        logging.error(e)
        gen.quit(1)
    else:

        happy = f"""
        
        Your project "{gen.name}" is successfully set up!

        (*＾▽＾)/ Happy coding...
        
        """
        print(happy)
        gen.quit(0)


if __name__ == "__main__":
    main()
