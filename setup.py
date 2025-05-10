from setuptools import setup, find_packages

setup(
    name="llm-coder",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "llm-coder=llm_coder.cli:run_cli",
        ],
    },
    description="LLM Coder CLI tool",
    author="Tomokatsu Iguchi",
    author_email="llm_coder@igtm.link",
    python_requires=">=3.7",
)
