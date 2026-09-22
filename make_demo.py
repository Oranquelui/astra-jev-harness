"""Compatibility entrypoint for the CLI synthetic repository generator."""
import runpy

if __name__ == "__main__":
    runpy.run_module("cli.make_demo", run_name="__main__")
else:
    from cli.make_demo import create
