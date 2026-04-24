"""Entry point: python -m everythingsearch"""

import sys

def main():
    # 为了向后兼容，如果没有任何参数，默认启动 Web 服务
    if len(sys.argv) == 1:
        from everythingsearch.app import main as app_main
        app_main()
        return

    command = sys.argv[1]

    if command == "serve":
        from everythingsearch.app import main as app_main
        app_main()
        return
        
    elif command == "search":
        from everythingsearch.cli import main as cli_main
        # 从 sys.argv 中移除 "search"，以便 cli.py 中的 argparse 能正常解析剩余参数
        sys.argv.pop(1)
        # 此时 sys.argv[0] 依然是脚本名，后续的元素是传给 search 的参数
        cli_main()
        return
        
    elif command in ("-h", "--help", "help"):
        print("Usage:")
        print("  python -m everythingsearch        启动 Web 服务 (默认)")
        print("  python -m everythingsearch serve  启动 Web 服务")
        print("  python -m everythingsearch search 执行命令行检索 (例如: search \"关于测试的文档\" --json)")
        sys.exit(0)
        
    else:
        print(f"Unknown command: {command}")
        print("Use 'python -m everythingsearch --help' for usage.")
        sys.exit(1)

if __name__ == "__main__":
    main()
