"""Эмулятор командной строки с графическим интерфейсом."""
import argparse
import getpass
import os
import re
import shlex
import socket
import sys
import xml.etree.ElementTree as xml_tree
import tkinter as tk
from datetime import datetime
from tkinter import scrolledtext

ENV_PATTERN = re.compile(r"\$(\w+)|\$\{(\w+)\}")
DELAY_MS = 400
NOT_SET = "<не задан>"
NOT_FOUND = "нет такого файла или каталога"
TAIL_LINES = 10
MIN_COUNT = 0
MAX_PATHS = 1


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


def default_vfs():
    """Создаёт VFS по умолчанию в памяти."""
    syslog = "".join(f"строка журнала {i}\n" for i in range(1, 16))
    return {
        "home": {
            "user": {
                "notes.txt": "Первая заметка\nВторая заметка\n",
                "projects": {"demo": {}},
            }
        },
        "etc": {"motd": "Добро пожаловать!\n"},
        "var": {"log": {"syslog": syslog}},
        "tmp": {},
    }


def read_dir(path):
    """Читает директорию с диска в словарь (всё хранится в памяти)."""
    tree = {}
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        if os.path.isdir(full):
            tree[name] = read_dir(full)
        else:
            with open(full, encoding="utf-8", errors="replace") as file:
                tree[name] = file.read()
    return tree


def load_vfs(path):
    """Загружает VFS из директории или создаёт VFS по умолчанию."""
    if path is None:
        return default_vfs()
    if not os.path.exists(path):
        raise ShellError(f"{path}: путь не найден")
    if not os.path.isdir(path):
        raise ShellError(f"{path}: неверный формат, нужна директория")
    try:
        return read_dir(path)
    except OSError as error:
        raise ShellError(f"{path}: {error.strerror}") from error


def tree_lines(tree, depth=0):
    """Строки с деревом каталогов и файлов для команды vfs-tree."""
    lines = []
    for name in sorted(tree):
        item = tree[name]
        if isinstance(item, dict):
            lines.append("  " * depth + name + "/")
            lines += tree_lines(item, depth + 1)
        else:
            lines.append("  " * depth + f"{name} ({len(item.encode())} B)")
    return lines


class XmlLog:
    """XML-журнал вызовов команд."""

    def __init__(self, path):
        """Создаёт лог-файл (и папку для него, если нужно)."""
        self.path = path
        self.root = xml_tree.Element("log")
        folder = os.path.dirname(path)
        try:
            if folder:
                os.makedirs(folder, exist_ok=True)
        except OSError as error:
            raise ShellError(f"{path}: {error.strerror}") from error
        self.save()

    def add(self, command, args, error):
        """Добавляет событие: время, команда, аргументы, ошибка."""
        event = xml_tree.SubElement(self.root, "event")
        stamp = datetime.now().isoformat(timespec="seconds")
        xml_tree.SubElement(event, "time").text = stamp
        xml_tree.SubElement(event, "command").text = command
        args_node = xml_tree.SubElement(event, "args")
        for arg in args:
            xml_tree.SubElement(args_node, "arg").text = arg
        xml_tree.SubElement(event, "error").text = error
        self.save()

    def save(self):
        """Записывает журнал в файл."""
        tree = xml_tree.ElementTree(self.root)
        xml_tree.indent(tree)
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

    def __init__(self, vfs, log=None):
        """Запоминает пользователя и хост из реальной ОС."""
        self.user = getpass.getuser()
        self.host = socket.gethostname()
        self.cwd = []
        self.running = True
        self.vfs = vfs
        self.log = log
        self.started = datetime.now()
        self.commands = {
            "ls": self.cmd_ls,
            "cd": self.cmd_cd,
            "vfs-tree": self.cmd_vfs_tree,
            "tail": self.cmd_tail,
            "who": self.cmd_who,
            "rmdir": self.cmd_rmdir,
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

    def resolve(self, path):
        """Превращает путь пользователя в список имён от корня."""
        parts = [] if path.startswith("/") else list(self.cwd)
        for part in path.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part not in ("", "."):
                parts.append(part)
        return parts

    def find(self, cmd, path):
        """Ищет путь в VFS, возвращает (части пути, узел)."""
        parts = self.resolve(path)
        node = self.vfs
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                raise ShellError(f"{cmd}: {path}: {NOT_FOUND}")
            node = node[part]
        return parts, node

    def cmd_ls(self, args):
        """ls [-l] [путь] - содержимое каталога."""
        long_format, paths = split_ls_args(args)
        _, node = self.find("ls", paths[0] if paths else ".")
        if not isinstance(node, dict):
            return paths[0]
        lines = [
            ls_line(name, node[name], long_format) for name in sorted(node)
        ]
        return ("\n" if long_format else "  ").join(lines)

    def cmd_cd(self, args):
        """cd [путь] - меняет текущий каталог."""
        if len(args) > MAX_PATHS:
            raise ShellError("cd: слишком много аргументов")
        path = args[0] if args else "/"
        parts, node = self.find("cd", path)
        if not isinstance(node, dict):
            raise ShellError(f"cd: {path}: не каталог")
        self.cwd = parts
        return ""

    def cmd_tail(self, args):
        """tail [-n N] файл - последние строки файла."""
        count = TAIL_LINES
        if args[:1] == ["-n"]:
            if not args[1:]:
                raise ShellError("tail: опция -n требует число")
            count = parse_count(args[1])
            args = args[2:]
        if not args or args[1:]:
            raise ShellError("tail: ожидается один файл")
        _, node = self.find("tail", args[0])
        if isinstance(node, dict):
            raise ShellError(f"tail: {args[0]}: это каталог")
        lines = node.splitlines()
        start = max(len(lines) - count, MIN_COUNT)
        return "\n".join(lines[start:])

    def cmd_who(self, args):
        """who - кто вошёл в систему (реальный пользователь ОС)."""
        if args:
            raise ShellError("who: лишние аргументы")
        return f"{self.user}  console  {self.started:%Y-%m-%d %H:%M}"

    def cmd_rmdir(self, args):
        """rmdir каталог... - удаляет пустые каталоги (в памяти)."""
        if not args:
            raise ShellError("rmdir: пропущен операнд")
        for path in args:
            parts, node = self.find("rmdir", path)
            if not parts:
                raise ShellError("rmdir: нельзя удалить корень")
            if not isinstance(node, dict):
                raise ShellError(f"rmdir: {path}: не каталог")
            if parts == self.cwd:
                raise ShellError(f"rmdir: {path}: это текущий каталог")
            if node:
                raise ShellError(f"rmdir: {path}: каталог не пуст")
            _, parent = self.find("rmdir", "/" + "/".join(parts[:-1]))
            del parent[parts[-1]]
        return ""

    def cmd_vfs_tree(self, args):
        """vfs-tree - служебная команда: показывает дерево VFS."""
        if args:
            raise ShellError("vfs-tree: команда не принимает аргументов")
        return "\n".join(["/"] + tree_lines(self.vfs))

    def cmd_exit(self, args):
        """exit - завершает работу эмулятора."""
        if args:
            raise ShellError("exit: команда не принимает аргументов")
        self.running = False
        return ""


def split_ls_args(args):
    """Делит аргументы ls на ключ -l и список путей."""
    paths = [arg for arg in args if arg != "-l"]
    for path in paths:
        if path.startswith("-"):
            raise ShellError(f"ls: неверный ключ {path}")
    if len(paths) > MAX_PATHS:
        raise ShellError("ls: слишком много аргументов")
    return "-l" in args, paths


def ls_line(name, item, long_format):
    """Строка вывода ls для одной записи каталога."""
    if not long_format:
        return name
    kind = "d" if isinstance(item, dict) else "-"
    size = 0 if kind == "d" else len(item.encode())
    return f"{kind} {size:>6} {name}"


def parse_count(text):
    """Преобразует аргумент -n в неотрицательное число."""
    try:
        count = int(text)
    except ValueError:
        raise ShellError(f"tail: неверное число строк: {text}") from None
    if count < MIN_COUNT:
        raise ShellError(f"tail: неверное число строк: {text}")
    return count


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
        vfs = load_vfs(args.vfs)
        log = XmlLog(args.log) if args.log else None
        script = read_script(args.script) if args.script else []
    except ShellError as error:
        print(f"Ошибка запуска: {error}", file=sys.stderr)
        return 1
    emu = Emulator(vfs, log)
    if args.headless:
        run_console(emu, script)
    else:
        App(emu, banner, script).root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
