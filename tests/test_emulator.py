"""Тесты эмулятора."""
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from emulator import Emulator, ShellError, XmlLog, expand_vars, parse_line
from emulator import read_script
from emulator import default_vfs, load_vfs


def make(log=None):
    """Создаёт эмулятор с VFS по умолчанию."""
    return Emulator(default_vfs(), log)


def run(emu, line):
    """Возвращает вывод команды или текст ошибки."""
    output, error = emu.execute(line)
    return output or error


class ParseTest(unittest.TestCase):
    """Разбор строки и переменные окружения."""

    def test_split(self):
        """Строка делится на слова."""
        self.assertEqual(parse_line("ls -l /tmp"), ["ls", "-l", "/tmp"])

    def test_env(self):
        """Переменные окружения раскрываются."""
        os.environ["EMU_TEST"] = "value"
        self.assertEqual(parse_line("cd $EMU_TEST"), ["cd", "value"])
        self.assertEqual(expand_vars("${EMU_TEST}/x"), "value/x")

    def test_unknown_variable(self):
        """Неизвестная переменная даёт пустую строку."""
        self.assertEqual(expand_vars("a$EMU_NO_SUCH b"), "a b")

    def test_unclosed_quote(self):
        """Незакрытая кавычка - ошибка."""
        with self.assertRaises(ShellError):
            parse_line('echo "abc')

    def test_comment(self):
        """Текст после # игнорируется."""
        self.assertEqual(parse_line("ls # note"), ["ls"])


class ShellTest(unittest.TestCase):
    """Общее поведение оболочки."""

    def test_title(self):
        """Заголовок содержит пользователя и хост."""
        self.assertIn("Эмулятор - [", make().title())

    def test_unknown_command(self):
        """Неизвестная команда даёт ошибку."""
        self.assertIn("не найдена", run(make(), "foo"))

    def test_exit(self):
        """exit останавливает эмулятор."""
        emu = make()
        emu.execute("exit")
        self.assertFalse(emu.running)

    def test_exit_with_arguments(self):
        """exit с аргументами - ошибка."""
        self.assertIn("аргументов", run(make(), "exit 1"))

    def test_stubs(self):
        """ls и cd - заглушки."""
        self.assertEqual(run(make(), "ls -l"), "ls: аргументы = ['-l']")
        self.assertEqual(run(make(), "cd /x"), "cd: аргументы = ['/x']")


class LogTest(unittest.TestCase):
    """XML-журнал и стартовый скрипт."""

    def test_log_events(self):
        """В журнале есть команда, аргументы, ошибка и время."""
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "sub", "log.xml")
            emu = make(XmlLog(path))
            emu.execute("ls -l")
            emu.execute("nope")
            events = ET.parse(path).getroot().findall("event")
        self.assertEqual(events[0].findtext("command"), "ls")
        self.assertEqual(events[0].find("args/arg").text, "-l")
        self.assertIn("не найдена", events[1].findtext("error"))
        self.assertTrue(events[1].findtext("time"))

    def test_script_skips_comments(self):
        """Комментарии и пустые строки пропускаются."""
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "s.emu")
            with open(path, "w", encoding="utf-8") as file:
                file.write("# c\n\nls\n  # d\nexit\n")
            self.assertEqual(read_script(path), ["ls", "exit"])

    def test_missing_script(self):
        """Нет скрипта - ошибка."""
        with self.assertRaises(ShellError):
            read_script("no_such_script.emu")


class VfsTest(unittest.TestCase):
    """Загрузка VFS."""

    def test_default(self):
        """VFS по умолчанию создаётся в памяти."""
        self.assertIn("home", default_vfs())

    def test_load_from_directory(self):
        """Директория с диска загружается в память."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "a"))
            path = os.path.join(root, "a", "f.txt")
            with open(path, "w", encoding="utf-8") as file:
                file.write("hello")
            tree = load_vfs(root)
        self.assertEqual(tree["a"]["f.txt"], "hello")

    def test_missing_path(self):
        """Нет директории - ошибка."""
        with self.assertRaises(ShellError):
            load_vfs("no_such_directory")

    def test_file_instead_of_directory(self):
        """Файл вместо директории - неверный формат."""
        with tempfile.NamedTemporaryFile() as file:
            with self.assertRaises(ShellError):
                load_vfs(file.name)

    def test_vfs_tree(self):
        """vfs-tree начинает вывод с корня."""
        self.assertTrue(run(make(), "vfs-tree").startswith("/"))


if __name__ == "__main__":
    unittest.main()
