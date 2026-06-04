from setuptools import setup, find_packages

setup(
    name="chat-sdk",
    version="0.1.0",
    description="Python client SDK for Chat Management API",
    packages=find_packages(),
    install_requires=[
        "httpx>=0.24.0",
        "websockets>=11.0.0"
    ],
    python_requires=">=3.7",
)
