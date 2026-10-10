"""Эмулятор командной строки с графическим интерфейсом."""
import argparse
import getpass
import os
import re
import shlex
import socket
import sys
import xml.etree.ElementTree as ET
import tkinter as tk
from datetime import datetime
from tkinter import scrolledtext

ENV_PATTERN = re.compile(r"\$(\w+)|\$\{(\w+)\}")
DELAY_MS = 400
NOT_SET = "<не задан>"


class ShellError(Exception):
    """Ошибка выполнения команды или запуска."""


def expand_vars(text):
    """Заменяет $VAR и ${VAR} значениями переменных окружения."""
    def replace(match):
        """Возвращает значение найденной переменной."""
        return os.environ.get(match.group(1) or match.group(2), "")

    return ENV_PATTERN.sub(replace, text)


def parse_line(line):
    """Делит строку на слова и раскрывает переменные окружения."""
    try:
        words = shlex.split(line, comments=True)
    except ValueError:
        raise ShellError("ошибка разбора: незакрытая кавычка") from None
    return [expand_vars(word) for word in words]


class XmlLog:
    """XML-журнал вызовов команд."""

    def __init__(self, path):
        """Создаёт лог-файл (и папку для него, если нужно)."""
        self.path = path
        self.root = ET.Element("log")
        folder = os.path.dirname(path)
        try:
            if folder:
                os.makedirs(folder, exist_ok=True)
        except OSError as error:
            raise ShellError(f"{path}: {error.strerror}") from error
        self.save()

    def add(self, command, args, error):
        """Добавляет событие: время, команда, аргументы, ошибка."""
        event = ET.SubElement(self.root, "event")
        stamp = datetime.now().isoformat(timespec="seconds")
        ET.SubElement(event, "time").text = stamp
        ET.SubElement(event, "command").text = command
        args_node = ET.SubElement(event, "args")
        for arg in args:
            ET.SubElement(args_node, "arg").text = arg
        ET.SubElement(event, "error").text = error
        self.save()

    def save(self):
        """Записывает журнал в файл."""
        tree = ET.ElementTree(self.root)
        ET.indent(tree)
        try:
            tree.write(self.path, encoding="utf-8", xml_declaration=True)
        except OSError as error:
            raise ShellError(f"{self.path}: {error.strerror}") from error


def read_script(path):
    """Читает стартовый скрипт без пустых строк и комментариев."""
    try:
        with open(path, encoding="utf-8-sig") as file:
            lines = file.read().splitlines()
    except OSError as error:
        raise ShellError(f"{path}: {error.strerror}") from error
    return [
        line for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


class Emulator:
    """Ядро эмулятора: текущий каталог, команды, журнал."""

    def __init__(self, log=None):
        """Запоминает пользователя и хост из реальной ОС."""
        self.user = getpass.getuser()
        self.host = socket.gethostname()
        self.cwd = []
        self.running = True
        self.log = log
        self.commands = {
            "ls": self.cmd_ls,
            "cd": self.cmd_cd,
            "exit": self.cmd_exit,
        }

    def title(self):
        """Заголовок окна из реальных данных ОС."""
        return f"Эмулятор - [{self.user}@{self.host}]"

    def prompt(self):
        """Приглашение к вводу."""
        path = "/" + "/".join(self.cwd)
        return f"{self.user}@{self.host}:{path}$"

    def execute(self, line):
        """Выполняет строку, возвращает (вывод, ошибка)."""
        name, args = line.strip(), []
        try:
            words = parse_line(line)
            if not words:
                return "", ""
            name, args = words[0], words[1:]
            if name not in self.commands:
                raise ShellError(f"{name}: команда не найдена")
            output = self.commands[name](args)
        except ShellError as error:
            self.write_log(name, args, str(error))
            return "", str(error)
        self.write_log(name, args, "")
        return output, ""

    def write_log(self, name, args, error):
        """Пишет событие в журнал, если он включён."""
        if self.log:
            self.log.add(name, args, error)

    def cmd_ls(self, args):
        """Заглушка ls: печатает имя и аргументы."""
        return f"ls: аргументы = {args}"

    def cmd_cd(self, args):
        """Заглушка cd: печатает имя и аргументы."""
        return f"cd: аргументы = {args}"

    def cmd_exit(self, args):
        """exit - завершает работу эмулятора."""
        if args:
            raise ShellError("exit: команда не принимает аргументов")
        self.running = False
        return ""


class App:
    """Окно эмулятора: вывод сверху, строка ввода снизу."""

    def __init__(self, emu, banner="", script=None):
        """Создаёт окно и все его элементы."""
        self.emu = emu
        self.script = list(script or [])
        self.root = tk.Tk()
        self.root.title(emu.title())
        self.output = scrolledtext.ScrolledText(
            self.root, width=90, height=28, state="disabled",
            bg="black", fg="white", font=("Courier", 11),
        )
        self.output.pack(fill="both", expand=True)
        self.output.tag_config("error", foreground="#ff6b6b")
        bottom = tk.Frame(self.root)
        bottom.pack(fill="x")
        self.label = tk.Label(bottom, font=("Courier", 11))
        self.label.pack(side="left")
        self.entry = tk.Entry(bottom, font=("Courier", 11))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self.on_enter)
        self.entry.focus_set()
        self.show(banner)
        self.label.config(text=emu.prompt())
        self.root.after(DELAY_MS, self.next_script_line)

    def show(self, text, tag=None):
        """Добавляет текст в область вывода."""
        if not text:
            return
        self.output.config(state="normal")
        self.output.insert("end", text + "\n", (tag,) if tag else ())
        self.output.see("end")
        self.output.config(state="disabled")

    def run_line(self, line):
        """Показывает ввод и результат команды; False после exit."""
        self.show(f"{self.emu.prompt()} {line}")
        output, error = self.emu.execute(line)
        self.show(output)
        self.show(error, "error")
        self.label.config(text=self.emu.prompt())
        if not self.emu.running:
            self.root.destroy()
            return False
        return True

    def on_enter(self, _event):
        """Обрабатывает нажатие Enter в строке ввода."""
        line = self.entry.get()
        self.entry.delete(0, "end")
        self.run_line(line)

    def next_script_line(self):
        """Выполняет очередную строку стартового скрипта."""
        if not self.script:
            return
        if self.run_line(self.script.pop(0)):
            self.root.after(DELAY_MS, self.next_script_line)


def show_step(emu, line):
    """Текстовый режим: выполняет строку и печатает диалог."""
    print(f"{emu.prompt()} {line}")
    output, error = emu.execute(line)
    if output:
        print(output)
    if error:
        print(error)
    return emu.running


def run_console(emu, script):
    """Текстовый режим: сначала скрипт, потом ввод с клавиатуры."""
    for line in script:
        if not show_step(emu, line):
            return
    for line in sys.stdin:
        if not show_step(emu, line.rstrip("\n")):
            return


def parse_args():
    """Разбирает параметры командной строки."""
    parser = argparse.ArgumentParser(description="Эмулятор командной строки")
    parser.add_argument("--vfs", help="путь к директории с VFS")
    parser.add_argument("--log", help="путь к XML лог-файлу")
    parser.add_argument("--script", help="путь к стартовому скрипту")
    parser.add_argument(
        "--headless", action="store_true", help="работа без окна"
    )
    return parser.parse_args()


def describe(args):
    """Отладочный вывод всех заданных параметров."""
    lines = ["[debug] Параметры запуска:"]
    for name in ("vfs", "log", "script", "headless"):
        value = getattr(args, name)
        if value is None:
            value = NOT_SET
        lines.append(f"[debug]   --{name} = {value}")
    return "\n".join(lines)


def main():
    """Запускает эмулятор, возвращает код завершения."""
    args = parse_args()
    banner = describe(args)
    print(banner)
    try:
        log = XmlLog(args.log) if args.log else None
        script = read_script(args.script) if args.script else []
    except ShellError as error:
        print(f"Ошибка запуска: {error}", file=sys.stderr)
        return 1
    emu = Emulator(log)
    if args.headless:
        run_console(emu, script)
    else:
        App(emu, banner, script).root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
