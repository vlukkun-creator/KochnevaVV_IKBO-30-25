"""Тесты эмулятора."""
import os
import tempfile
import unittest
import xml.etree.ElementTree as xml_tree

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


class LogTest(unittest.TestCase):
    """XML-журнал и стартовый скрипт."""

    def test_log_events(self):
        """В журнале есть команда, аргументы, ошибка и время."""
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "sub", "log.xml")
            emu = make(XmlLog(path))
            emu.execute("ls -l")
            emu.execute("nope")
            events = xml_tree.parse(path).getroot().findall("event")
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

TAIL_DEFAULT = 10
TAIL_THREE = 3


class CommandsTest(unittest.TestCase):
    """Команды ls, cd, tail, who."""

    def test_ls(self):
        """ls показывает каталоги корня."""
        self.assertEqual(run(make(), "ls"), "etc  home  tmp  var")

    def test_ls_long_and_file(self):
        """ls -l показывает тип и размер, ls файл - имя файла."""
        self.assertTrue(run(make(), "ls -l /home").startswith("d"))
        self.assertEqual(run(make(), "ls /etc/motd"), "/etc/motd")

    def test_ls_errors(self):
        """ls сообщает об ошибках."""
        self.assertIn("нет такого", run(make(), "ls /nope"))
        self.assertIn("ключ", run(make(), "ls -z"))
        self.assertIn("много", run(make(), "ls /etc /tmp"))

    def test_cd(self):
        """cd работает с относительными путями и .."""
        emu = make()
        emu.execute("cd home/user")
        self.assertEqual(emu.cwd, ["home", "user"])
        emu.execute("cd ../..")
        self.assertEqual(emu.cwd, [])

    def test_cd_errors(self):
        """cd в файл и в несуществующий каталог - ошибка."""
        self.assertIn("не каталог", run(make(), "cd /etc/motd"))
        self.assertIn("нет такого", run(make(), "cd /nope"))

    def test_tail(self):
        """tail по умолчанию 10 строк, с -n 3 - три."""
        lines = run(make(), "tail /var/log/syslog").splitlines()
        self.assertEqual(len(lines), TAIL_DEFAULT)
        lines = run(make(), "tail -n 3 /var/log/syslog").splitlines()
        self.assertEqual(len(lines), TAIL_THREE)

    def test_tail_errors(self):
        """tail сообщает об ошибках."""
        self.assertIn("неверное", run(make(), "tail -n x /etc/motd"))
        self.assertIn("один файл", run(make(), "tail"))
        self.assertIn("каталог", run(make(), "tail /etc"))
        self.assertIn("нет такого", run(make(), "tail /nope"))

    def test_who(self):
        """who показывает пользователя; лишние аргументы - ошибка."""
        self.assertIn("console", run(make(), "who"))
        self.assertIn("лишние", run(make(), "who x"))


class RmdirTest(unittest.TestCase):
    """Команда rmdir."""

    def test_remove(self):
        """rmdir удаляет пустой каталог из памяти."""
        emu = make()
        self.assertEqual(run(emu, "rmdir /tmp"), "")
        self.assertIn("нет такого", run(emu, "ls /tmp"))

    def test_errors(self):
        """rmdir не удаляет непустые, файлы, текущий каталог."""
        emu = make()
        self.assertIn("не пуст", run(emu, "rmdir /home"))
        self.assertIn("не каталог", run(emu, "rmdir /etc/motd"))
        self.assertIn("операнд", run(emu, "rmdir"))
        self.assertIn("корень", run(emu, "rmdir /"))
        emu.execute("cd /tmp")
        self.assertIn("текущий", run(emu, "rmdir ."))


if __name__ == "__main__":
    unittest.main()
