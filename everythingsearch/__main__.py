"""Entry point: python -m everythingsearch"""

import sys


def _print_help() -> None:
    print("Usage:")
    print('  python -m everythingsearch search  执行命令行检索 (例如: search "关于测试的文档" --json)')
    print("")
    print("启动搜索服务请使用: ./scripts/run_app.sh start")


def main():
    if len(sys.argv) == 1 or sys.argv[1] in ("-h", "--help", "help"):
        _print_help()
        sys.exit(0 if len(sys.argv) > 1 else 1)

    command = sys.argv[1]

    if command == "search":
        from everythingsearch.cli import main as cli_main

        sys.argv.pop(1)
        cli_main()
        return

    print(f"Unknown command: {command}")
    _print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
