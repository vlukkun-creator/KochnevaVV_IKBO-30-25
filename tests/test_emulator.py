"""Тесты эмулятора."""
import os
import unittest

from emulator import Emulator, ShellError, expand_vars, parse_line


def make():
    """Создаёт эмулятор для теста."""
    return Emulator()


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


if __name__ == "__main__":
    unittest.main()
