"""Эмулятор командной строки с графическим интерфейсом."""
import getpass
import os
import re
import shlex
import socket
import tkinter as tk
from tkinter import scrolledtext

ENV_PATTERN = re.compile(r"\$(\w+)|\$\{(\w+)\}")


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


class Emulator:
    """Ядро эмулятора: текущий каталог, команды, журнал."""

    def __init__(self):
        """Запоминает пользователя и хост из реальной ОС."""
        self.user = getpass.getuser()
        self.host = socket.gethostname()
        self.cwd = []
        self.running = True
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
        try:
            words = parse_line(line)
            if not words:
                return "", ""
            name, args = words[0], words[1:]
            if name not in self.commands:
                raise ShellError(f"{name}: команда не найдена")
            output = self.commands[name](args)
        except ShellError as error:
            return "", str(error)
        return output, ""

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

    def __init__(self, emu):
        """Создаёт окно и все его элементы."""
        self.emu = emu
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
        self.label.config(text=emu.prompt())

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


def main():
    """Запускает окно эмулятора."""
    App(Emulator()).root.mainloop()


if __name__ == "__main__":
    main()
