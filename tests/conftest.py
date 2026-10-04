import pytest


def pytest_addoption(parser):
    parser.addoption("--hil", action="store_true", help="run hardware-in-the-loop tests")


def _cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def pytest_collection_modifyitems(config, items):
    skips = {"hil": (not config.getoption("--hil"), "needs --hil and the real robot"),
             "gpu": (not _cuda(), "needs a CUDA GPU")}
    for item in items:
        for mark, (skip, why) in skips.items():
            if skip and mark in item.keywords:
                item.add_marker(pytest.mark.skip(reason=why))
