import threading

from apps.notifications.push import background
from apps.notifications.push.background import run_in_background


def test_the_task_runs_in_another_thread():
    seen = []

    run_in_background(lambda: seen.append(threading.current_thread()), where="la prueba").result(5)

    assert seen[0] is not threading.main_thread()
    assert seen[0].name.startswith("push")


def test_the_task_receives_its_arguments():
    seen = []

    run_in_background(lambda a, b=None: seen.append((a, b)), 1, b=2, where="la prueba").result(5)

    assert seen == [(1, 2)]


def test_a_failure_is_logged_and_does_not_break_the_caller(monkeypatch):
    logged = []
    monkeypatch.setattr(
        background, "log_unhandled_error", lambda exc, where: logged.append((type(exc), where))
    )

    def broken():
        raise RuntimeError("sin red")

    run_in_background(broken, where="la push de prueba").result(5)

    assert logged == [(RuntimeError, "la push de prueba")]


def test_the_connection_of_the_thread_is_closed_even_when_the_task_fails(monkeypatch):
    closed = []
    monkeypatch.setattr(background.connections, "close_all", lambda: closed.append(True))
    monkeypatch.setattr(background, "log_unhandled_error", lambda exc, where: None)

    run_in_background(lambda: None, where="la prueba").result(5)
    run_in_background(lambda: 1 / 0, where="la prueba").result(5)

    assert closed == [True, True]
