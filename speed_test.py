#!/usr/bin/env python3
"""Измеряет скорость скачивания по десяти последовательным HTTP-запросам."""

import argparse
import sys
from http.client import HTTPException
from time import perf_counter
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


REQUEST_COUNT = 10
# Читаем по 64 KiB, чтобы не делать слишком много мелких чтений и не занимать много памяти.
CHUNK_SIZE = 64 * 1024
TIMEOUT_SECONDS = 30


def validate_url(value):
    """Проверяет URL из командной строки перед началом замера."""
    try:
        parsed = urlsplit(value)
        if parsed.scheme in ("http", "https") and parsed.hostname and parsed.port != 0:
            return value
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Укажите полный URL с http:// или https://")


def download(url):
    """Полностью читает один ответ, не сохраняя его целиком в памяти."""
    request = Request(url, headers={
        "Accept-Encoding": "identity",
        "User-Agent": "EtoLegkoSpeedTest/1.0",
    })
    started = perf_counter()
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        expected = response.headers.get("Content-Length")
        if response.headers.get("Transfer-Encoding") or response.status in (204, 304):
            expected = None
        expected = int(expected) if expected is not None else None
        received = 0
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            received += len(chunk)
        if expected is not None and received != expected:
            raise HTTPException(
                f"Неполный ответ: ожидалось {expected} байт, получено {received}"
            )
    return perf_counter() - started, received


def measure(url):
    """Последовательно скачивает десять ответов и суммирует время и объём."""
    total_seconds = 0.0
    total_bytes = 0
    for index in range(1, REQUEST_COUNT + 1):
        print(f"Запрос {index}/{REQUEST_COUNT}: скачивание…", file=sys.stderr, flush=True)
        try:
            elapsed, size = download(url)
        except (URLError, HTTPException, OSError, ValueError) as error:
            raise OSError(f"Запрос {index}/{REQUEST_COUNT}: {error}") from error
        total_seconds += elapsed
        total_bytes += size
    if total_bytes == 0:
        raise OSError("Нет данных для измерения скорости: все ответы пустые")
    return total_seconds, total_bytes


def main():
    parser = argparse.ArgumentParser(
        description="Оценка скорости скачивания по 10 последовательным запросам."
    )
    parser.add_argument("url", type=validate_url, help="URL файла для скачивания")
    args = parser.parse_args()

    try:
        total_seconds, total_bytes = measure(args.url)
    except OSError as error:
        print(f"Не удалось завершить замер: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nЗамер прерван.", file=sys.stderr)
        return 130

    print(f"Запросов: {REQUEST_COUNT}")
    print(f"Среднее время запроса: {total_seconds / REQUEST_COUNT:.3f} с")
    print(f"Скачано: {total_bytes} байт ({total_bytes / 1024**2:.3f} MiB)")
    print(f"Скорость скачивания: {total_bytes * 8 / total_seconds / 1_000_000:.3f} Мбит/с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
