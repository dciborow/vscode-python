# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

from __future__ import print_function, unicode_literals

try:
    from io import StringIO
except ImportError:
    from StringIO import StringIO  # type: ignore (for Pylance)
import os
import sys
import tempfile
import unittest

import pytest
import _pytest.doctest

from .... import util
from testing_tools.adapter import util as adapter_util
from testing_tools.adapter.pytest import _pytest_item as pytest_item
from testing_tools.adapter import info
from testing_tools.adapter.pytest import _discovery

# In Python 3.8 __len__ is called twice, which impacts some of the test assertions we do below.
PYTHON_38_OR_LATER = sys.version_info[0] >= 3 and sys.version_info[1] >= 8


class StubPyTest(util.StubProxy):
    def __init__(self, stub=None):
        super(StubPyTest, self).__init__(stub, "pytest")
        self.return_main = 0

    def main(self, args, plugins):
        self.add_call("main", None, {"args": args, "plugins": plugins})
        return self.return_main


class StubPlugin(util.StubProxy):

    _started = True

    def __init__(self, stub=None, tests=None):
        super(StubPlugin, self).__init__(stub, "plugin")
        if tests is None:
            tests = StubDiscoveredTests(self.stub)
        self._tests = tests

    def __getattr__(self, name):
        if not name.startswith("pytest_"):
            raise AttributeError(name)

        def func(*args, **kwargs):
            self.add_call(name, args or None, kwargs or None)

        return func


class StubDiscoveredTests(util.StubProxy):

    NOT_FOUND = object()

    def __init__(self, stub=None):
        super(StubDiscoveredTests, self).__init__(stub, "discovered")
        self.return_items = []
        self.return_parents = []

    def __len__(self):
        self.add_call("__len__", None, None)
        return len(self.return_items)

    def __getitem__(self, index):
        self.add_call("__getitem__", (index,), None)
        return self.return_items[index]

    @property
    def parents(self):
        self.add_call("parents", None, None)
        return self.return_parents

    def reset(self):
        self.add_call("reset", None, None)

    def add_test(self, test, parents):
        self.add_call("add_test", None, {"test": test, "parents": parents})


class FakeFunc(object):
    def __init__(self, name):
        self.__name__ = name


class FakeMarker(object):
    def __init__(self, name):
        self.name = name


class StubPytestItem(util.StubProxy):

    _debugging = False
    _hasfunc = True

    def __init__(self, stub=None, **attrs):
        super(StubPytestItem, self).__init__(stub, "pytest.Item")
        if attrs.get("function") is None:
            attrs.pop("function", None)
            self._hasfunc = False

        attrs.setdefault("user_properties", [])

        slots = getattr(type(self), "__slots__", None)
        if slots:
            for name, value in attrs.items():
                if name in self.__slots__:
                    setattr(self, name, value)
                else:
                    self.__dict__[name] = value
        else:
            self.__dict__.update(attrs)

        if "own_markers" not in attrs:
            self.own_markers = ()

    def __repr__(self):
        return object.__repr__(self)

    def __getattr__(self, name):
        if not self._debugging:
            self.add_call(name + " (attr)", None, None)
        if name == "function":
            if not self._hasfunc:
                raise AttributeError(name)

        def func(*args, **kwargs):
            self.add_call(name, args or None, kwargs or None)

        return func


class StubSubtypedItem(StubPytestItem):
    @classmethod
    def from_args(cls, *args, **kwargs):
        if not hasattr(cls, "from_parent"):
            return cls(*args, **kwargs)
        self = cls.from_parent(None, name=kwargs["name"], runner=None, dtest=None)
        self.__init__(*args, **kwargs)
        return self

    def __init__(self, *args, **kwargs):
        super(StubSubtypedItem, self).__init__(*args, **kwargs)
        if "nodeid" in self.__dict__:
            self._nodeid = self.__dict__.pop("nodeid")

    @property
    def location(self):
        return self.__dict__.get("location")


class StubFunctionItem(StubSubtypedItem, pytest.Function):
    @property
    def function(self):
        return self.__dict__.get("function")


def create_stub_function_item(*args, **kwargs):
    return StubFunctionItem.from_args(*args, **kwargs)


class StubDoctestItem(StubSubtypedItem, _pytest.doctest.DoctestItem):
    pass


def create_stub_doctest_item(*args, **kwargs):
    return StubDoctestItem.from_args(*args, **kwargs)


class StubPytestSession(util.StubProxy):
    def __init__(self, stub=None):
        super(StubPytestSession, self).__init__(stub, "pytest.Session")

    def __getattr__(self, name):
        self.add_call(name + " (attr)", None, None)

        def func(*args, **kwargs):
            self.add_call(name, args or None, kwargs or None)

        return func


class StubPytestConfig(util.StubProxy):
    def __init__(self, stub=None):
        super(StubPytestConfig, self).__init__(stub, "pytest.Config")

    def __getattr__(self, name):
        self.add_call(name + " (attr)", None, None)

        def func(*args, **kwargs):
            self.add_call(name, args or None, kwargs or None)

        return func


def generate_parse_item(pathsep):
    if pathsep == "\\":

        def normcase(path):
            path = path.lower()
            return path.replace("/", "\\")

    else:
        raise NotImplementedError
    ##########
    def _fix_fileid(*args):
        return adapter_util.fix_fileid(
            *args,
            **dict(
                # dependency injection
                _normcase=normcase,
                _pathsep=pathsep,
            )
        )

    def _normalize_test_id(*args):
        return pytest_item._normalize_test_id(
            *args,
            **dict(
                # dependency injection
                _fix_fileid=_fix_fileid,
                _pathsep=pathsep,
            )
        )

    def _iter_nodes(*args):
        return pytest_item._iter_nodes(
            *args,
            **dict(
                # dependency injection
                _normalize_test_id=_normalize_test_id,
                _normcase=normcase,
                _pathsep=pathsep,
            )
        )

    def _parse_node_id(*args):
        return pytest_item._parse_node_id(
            *args,
            **dict(
                # dependency injection
                _iter_nodes=_iter_nodes,
            )
        )

    ##########
    def _split_fspath(*args):
        return pytest_item._split_fspath(
            *args,
            **dict(
                # dependency injection
                _normcase=normcase,
            )
        )

    ##########
    def _matches_relfile(*args):
        return pytest_item._matches_relfile(
            *args,
            **dict(
                # dependency injection
                _normcase=normcase,
                _pathsep=pathsep,
            )
        )

    def _is_legacy_wrapper(*args):
        return pytest_item._is_legacy_wrapper(
            *args,
            **dict(
                # dependency injection
                _pathsep=pathsep,
            )
        )

    def _get_location(*args):
        return pytest_item._get_location(
            *args,
            **dict(
                # dependency injection
                _matches_relfile=_matches_relfile,
                _is_legacy_wrapper=_is_legacy_wrapper,
                _pathsep=pathsep,
            )
        )

    ##########
    def _parse_item(item):
        return pytest_item.parse_item(
            item,
            **dict(
                # dependency injection
                _parse_node_id=_parse_node_id,
                _split_fspath=_split_fspath,
                _get_location=_get_location,
            )
        )

    return _parse_item


##################################
# tests


def fake_pytest_main(stub, use_fd, pytest_stdout):
    def ret(args, plugins):
        stub.add_call("pytest.main", None, {"args": args, "plugins": plugins})
        if use_fd:
            os.write(sys.stdout.fileno(), pytest_stdout.encode())
        else:
            print(pytest_stdout, end="")
        return 0

    return ret


class DiscoverTests(unittest.TestCase):

    DEFAULT_ARGS = [
        "--collect-only",
    ]

    def test_basic(self):
        stub = util.Stub()
        stubpytest = StubPyTest(stub)
        plugin = StubPlugin(stub)
        expected = []
        plugin.discovered = expected
        calls = [
            ("pytest.main", None, {"args": self.DEFAULT_ARGS, "plugins": [plugin]}),
            ("discovered.parents", None, None),
            ("discovered.__len__", None, None),
            ("discovered.__getitem__", (0,), None),
        ]

        # In Python 3.8 __len__ is called twice.
        if PYTHON_38_OR_LATER:
            calls.insert(3, ("discovered.__len__", None, None))

        parents, tests = _discovery.discover(
            [], _pytest_main=stubpytest.main, _plugin=plugin
        )

        self.assertEqual(parents, [])
        self.assertEqual(tests, expected)
        self.assertEqual(stub.calls, calls)

    def test_failure(self):
        stub = util.Stub()
        pytest = StubPyTest(stub)
        pytest.return_main = 2
        plugin = StubPlugin(stub)

        with self.assertRaises(Exception):
            _discovery.discover([], _pytest_main=pytest.main, _plugin=plugin)

        self.assertEqual(
            stub.calls,
            [
                # There's only one call.
                ("pytest.main", None, {"args": self.DEFAULT_ARGS, "plugins": [plugin]}),
            ],
        )

    def test_no_tests_found(self):
        stub = util.Stub()
        pytest = StubPyTest(stub)
        pytest.return_main = 5
        plugin = StubPlugin(stub)
        expected = []
        plugin.discovered = expected
        calls = [
            ("pytest.main", None, {"args": self.DEFAULT_ARGS, "plugins": [plugin]}),
            ("discovered.parents", None, None),
            ("discovered.__len__", None, None),
            ("discovered.__getitem__", (0,), None),
        ]

        # In Python 3.8 __len__ is called twice.
        if PYTHON_38_OR_LATER:
            calls.insert(3, ("discovered.__len__", None, None))

        parents, tests = _discovery.discover(
            [], _pytest_main=pytest.main, _plugin=plugin
        )

        self.assertEqual(parents, [])
        self.assertEqual(tests, expected)
        self.assertEqual(stub.calls, calls)

    def test_stdio_hidden_file(self):
        stub = util.Stub()

        plugin = StubPlugin(stub)
        plugin.discovered = []
        calls = [
            ("pytest.main", None, {"args": self.DEFAULT_ARGS, "plugins": [plugin]}),
            ("discovered.parents", None, None),
            ("discovered.__len__", None, None),
            ("discovered.__getitem__", (0,), None),
        ]
        pytest_stdout = "spamspamspamspamspamspamspammityspam"

        # In Python 3.8 __len__ is called twice.
        if PYTHON_38_OR_LATER:
            calls.insert(3, ("discovered.__len__", None, None))

        # to simulate stdio behavior in methods like os.dup,
        # use actual files (rather than StringIO)
        with tempfile.TemporaryFile("r+") as mock:
            sys.stdout = mock
            try:
                _discovery.discover(
                    [],
                    hidestdio=True,
                    _pytest_main=fake_pytest_main(stub, False, pytest_stdout),
                    _plugin=plugin,
                )
            finally:
                sys.stdout = sys.__stdout__

            mock.seek(0)
            captured = mock.read()

        self.assertEqual(captured, "")
        self.assertEqual(stub.calls, calls)

    def test_stdio_hidden_fd(self):
        # simulate cases where stdout comes from the lower layer than sys.stdout
        # via file descriptors (e.g., from cython)
        stub = util.Stub()
        plugin = StubPlugin(stub)
        pytest_stdout = "spamspamspamspamspamspamspammityspam"

        # Replace with contextlib.redirect_stdout() once Python 2.7 support is dropped.
        sys.stdout = StringIO()
        try:
            _discovery.discover(
                [],
                hidestdio=True,
                _pytest_main=fake_pytest_main(stub, True, pytest_stdout),
                _plugin=plugin,
            )
            captured = sys.stdout.read()
            self.assertEqual(captured, "")
        finally:
            sys.stdout = sys.__stdout__

    def test_stdio_not_hidden_file(self):
        stub = util.Stub()

        plugin = StubPlugin(stub)
        plugin.discovered = []
        calls = [
            ("pytest.main", None, {"args": self.DEFAULT_ARGS, "plugins": [plugin]}),
            ("discovered.parents", None, None),
            ("discovered.__len__", None, None),
            ("discovered.__getitem__", (0,), None),
        ]
        pytest_stdout = "spamspamspamspamspamspamspammityspam"

        # In Python 3.8 __len__ is called twice.
        if PYTHON_38_OR_LATER:
            calls.insert(3, ("discovered.__len__", None, None))

        buf = StringIO()

        sys.stdout = buf
        try:
            _discovery.discover(
                [],
                hidestdio=False,
                _pytest_main=fake_pytest_main(stub, False, pytest_stdout),
                _plugin=plugin,
            )
        finally:
            sys.stdout = sys.__stdout__
        captured = buf.getvalue()

        self.assertEqual(captured, pytest_stdout)
        self.assertEqual(stub.calls, calls)

    def test_stdio_not_hidden_fd(self):
        # simulate cases where stdout comes from the lower layer than sys.stdout
        # via file descriptors (e.g., from cython)
        stub = util.Stub()
        plugin = StubPlugin(stub)
        pytest_stdout = "spamspamspamspamspamspamspammityspam"
        stub.calls = []
        with tempfile.TemporaryFile("r+") as mock:
            sys.stdout = mock
            try:
                _discovery.discover(
                    [],
                    hidestdio=False,
                    _pytest_main=fake_pytest_main(stub, True, pytest_stdout),
                    _plugin=plugin,
                )
            finally:
                mock.seek(0)
                captured = sys.stdout.read()
                sys.stdout = sys.__stdout__
        self.assertEqual(captured, pytest_stdout)


class CollectorTests(unittest.TestCase):
    def test_modifyitems(self):
        stub = util.Stub()
        discovered = StubDiscoveredTests(stub)
        session = StubPytestSession(stub)
        config = StubPytestConfig(stub)
        collector = _discovery.TestCollector(tests=discovered)

        testroot = adapter_util.fix_path("/a/b/c")
        relfile1 = adapter_util.fix_path("./test_spam.py")
        relfile2 = adapter_util.fix_path("x/y/z/test_eggs.py")

        collector.pytest_collection_modifyitems(
            session,
            config,
            [
                create_stub_function_item(
                    stub,
                    nodeid="test_spam.py::SpamTests::test_one",
                    name="test_one",
                    originalname=None,
                    location=("test_spam.py", 12, "SpamTests.test_one"),
                    fspath=adapter_util.PATH_JOIN(testroot, "test_spam.py"),
                    function=FakeFunc("test_one"),
                ),
                create_stub_function_item(
                    stub,
                    nodeid="test_spam.py::SpamTests::test_other",
                    name="test_other",
                    originalname=None,
                    location=("test_spam.py", 19, "SpamTests.test_other"),
                    fspath=adapter_util.PATH_JOIN(testroot, "test_spam.py"),
                    function=FakeFunc("test_other"),
                ),
                create_stub_function_item(
                    stub,
                    nodeid="test_spam.py::test_all",
                    name="test_all",
                    originalname=None,
                    location=("test_spam.py", 144, "test_all"),
                    fspath=adapter_util.PATH_JOIN(testroot, "test_spam.py"),
                    function=FakeFunc("test_all"),
                ),
                create_stub_function_item(
                    stub,
                    nodeid="test_spam.py::test_each[10-10]",
                    name="test_each[10-10]",
                    originalname="test_each",
                    location=("test_spam.py", 273, "test_each[10-10]"),
                    fspath=adapter_util.PATH_JOIN(testroot, "test_spam.py"),
                    function=FakeFunc("test_each"),
                ),
                create_stub_function_item(
                    stub,
                    nodeid=f'{relfile2}::All::BasicTests::test_first',
                    name="test_first",
                    originalname=None,
                    location=(relfile2, 31, "All.BasicTests.test_first"),
                    fspath=adapter_util.PATH_JOIN(testroot, relfile2),
                    function=FakeFunc("test_first"),
                ),
                create_stub_function_item(
                    stub,
                    nodeid=f'{relfile2}::All::BasicTests::test_each[1+2-3]',
                    name="test_each[1+2-3]",
                    originalname="test_each",
                    location=(relfile2, 62, "All.BasicTests.test_each[1+2-3]"),
                    fspath=adapter_util.PATH_JOIN(testroot, relfile2),
                    function=FakeFunc("test_each"),
                    own_markers=[
                        FakeMarker(v)
                        for v in [
                            # supported
                            "skip",
                            "skipif",
                            "xfail",
                            # duplicate
                            "skip",
                            # ignored (pytest-supported)
                            "parameterize",
                            "usefixtures",
                            "filterwarnings",
                            # ignored (custom)
                            "timeout",
                        ]
                    ],
                ),
            ],
        )


        self.maxDiff = None
        self.assertEqual(
            stub.calls,
            [
                ("discovered.reset", None, None),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            ("./test_spam.py::SpamTests", "SpamTests", "suite"),
                            ("./test_spam.py", "test_spam.py", "file"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./test_spam.py::SpamTests::test_one",
                            name="test_one",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=relfile1,
                                func="SpamTests.test_one",
                                sub=None,
                            ),
                            source=f"{relfile1}:13",
                            markers=None,
                            parentid="./test_spam.py::SpamTests",
                        ),
                    ),
                ),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            ("./test_spam.py::SpamTests", "SpamTests", "suite"),
                            ("./test_spam.py", "test_spam.py", "file"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./test_spam.py::SpamTests::test_other",
                            name="test_other",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=relfile1,
                                func="SpamTests.test_other",
                                sub=None,
                            ),
                            source=f"{relfile1}:20",
                            markers=None,
                            parentid="./test_spam.py::SpamTests",
                        ),
                    ),
                ),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            ("./test_spam.py", "test_spam.py", "file"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./test_spam.py::test_all",
                            name="test_all",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=relfile1,
                                func="test_all",
                                sub=None,
                            ),
                            source=f"{relfile1}:145",
                            markers=None,
                            parentid="./test_spam.py",
                        ),
                    ),
                ),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            ("./test_spam.py::test_each", "test_each", "function"),
                            ("./test_spam.py", "test_spam.py", "file"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./test_spam.py::test_each[10-10]",
                            name="test_each[10-10]",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=relfile1,
                                func="test_each",
                                sub=["[10-10]"],
                            ),
                            source=f"{relfile1}:274",
                            markers=None,
                            parentid="./test_spam.py::test_each",
                        ),
                    ),
                ),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (
                                "./x/y/z/test_eggs.py::All::BasicTests",
                                "BasicTests",
                                "suite",
                            ),
                            ("./x/y/z/test_eggs.py::All", "All", "suite"),
                            ("./x/y/z/test_eggs.py", "test_eggs.py", "file"),
                            ("./x/y/z", "z", "folder"),
                            ("./x/y", "y", "folder"),
                            ("./x", "x", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./x/y/z/test_eggs.py::All::BasicTests::test_first",
                            name="test_first",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=adapter_util.fix_relpath(relfile2),
                                func="All.BasicTests.test_first",
                                sub=None,
                            ),
                            source=f"{adapter_util.fix_relpath(relfile2)}:32",
                            markers=None,
                            parentid="./x/y/z/test_eggs.py::All::BasicTests",
                        ),
                    ),
                ),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (
                                "./x/y/z/test_eggs.py::All::BasicTests::test_each",
                                "test_each",
                                "function",
                            ),
                            (
                                "./x/y/z/test_eggs.py::All::BasicTests",
                                "BasicTests",
                                "suite",
                            ),
                            ("./x/y/z/test_eggs.py::All", "All", "suite"),
                            ("./x/y/z/test_eggs.py", "test_eggs.py", "file"),
                            ("./x/y/z", "z", "folder"),
                            ("./x/y", "y", "folder"),
                            ("./x", "x", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./x/y/z/test_eggs.py::All::BasicTests::test_each[1+2-3]",
                            name="test_each[1+2-3]",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=adapter_util.fix_relpath(relfile2),
                                func="All.BasicTests.test_each",
                                sub=["[1+2-3]"],
                            ),
                            source=f"{adapter_util.fix_relpath(relfile2)}:63",
                            markers=["expected-failure", "skip", "skip-if"],
                            parentid="./x/y/z/test_eggs.py::All::BasicTests::test_each",
                        ),
                    ),
                ),
            ],
        )

    def test_finish(self):
        stub = util.Stub()
        discovered = StubDiscoveredTests(stub)
        session = StubPytestSession(stub)
        testroot = adapter_util.fix_path("/a/b/c")
        relfile = adapter_util.fix_path("x/y/z/test_eggs.py")
        session.items = [
            create_stub_function_item(
                stub,
                nodeid=f'{relfile}::SpamTests::test_spam',
                name="test_spam",
                originalname=None,
                location=(relfile, 12, "SpamTests.test_spam"),
                fspath=adapter_util.PATH_JOIN(testroot, relfile),
                function=FakeFunc("test_spam"),
            )
        ]

        collector = _discovery.TestCollector(tests=discovered)

        collector.pytest_collection_finish(session)

        self.maxDiff = None
        self.assertEqual(
            stub.calls,
            [
                ("discovered.reset", None, None),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (
                                "./x/y/z/test_eggs.py::SpamTests",
                                "SpamTests",
                                "suite",
                            ),
                            ("./x/y/z/test_eggs.py", "test_eggs.py", "file"),
                            ("./x/y/z", "z", "folder"),
                            ("./x/y", "y", "folder"),
                            ("./x", "x", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./x/y/z/test_eggs.py::SpamTests::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=adapter_util.fix_relpath(relfile),
                                func="SpamTests.test_spam",
                                sub=None,
                            ),
                            source=f"{adapter_util.fix_relpath(relfile)}:13",
                            markers=None,
                            parentid="./x/y/z/test_eggs.py::SpamTests",
                        ),
                    ),
                ),
            ],
        )

    def test_doctest(self):
        stub = util.Stub()
        discovered = StubDiscoveredTests(stub)
        session = StubPytestSession(stub)
        testroot = adapter_util.fix_path("/a/b/c")
        doctestfile = adapter_util.fix_path("x/test_doctest.txt")
        relfile = adapter_util.fix_path("x/y/z/test_eggs.py")
        session.items = [
            create_stub_doctest_item(
                stub,
                nodeid=f'{doctestfile}::test_doctest.txt',
                name="test_doctest.txt",
                location=(doctestfile, 0, "[doctest] test_doctest.txt"),
                fspath=adapter_util.PATH_JOIN(testroot, doctestfile),
            ),
            create_stub_doctest_item(
                stub,
                nodeid=f'{relfile}::test_eggs',
                name="test_eggs",
                location=(relfile, 0, "[doctest] test_eggs"),
                fspath=adapter_util.PATH_JOIN(testroot, relfile),
            ),
            create_stub_doctest_item(
                stub,
                nodeid=f'{relfile}::test_eggs.TestSpam',
                name="test_eggs.TestSpam",
                location=(relfile, 12, "[doctest] test_eggs.TestSpam"),
                fspath=adapter_util.PATH_JOIN(testroot, relfile),
            ),
            create_stub_doctest_item(
                stub,
                nodeid=f'{relfile}::test_eggs.TestSpam.TestEggs',
                name="test_eggs.TestSpam.TestEggs",
                location=(relfile, 27, "[doctest] test_eggs.TestSpam.TestEggs"),
                fspath=adapter_util.PATH_JOIN(testroot, relfile),
            ),
        ]

        collector = _discovery.TestCollector(tests=discovered)

        collector.pytest_collection_finish(session)

        self.maxDiff = None
        self.assertEqual(
            stub.calls,
            [
                ("discovered.reset", None, None),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            ("./x/test_doctest.txt", "test_doctest.txt", "file"),
                            ("./x", "x", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./x/test_doctest.txt::test_doctest.txt",
                            name="test_doctest.txt",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=adapter_util.fix_relpath(doctestfile),
                                func=None,
                            ),
                            source=f"{adapter_util.fix_relpath(doctestfile)}:1",
                            markers=[],
                            parentid="./x/test_doctest.txt",
                        ),
                    ),
                ),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            ("./x/y/z/test_eggs.py", "test_eggs.py", "file"),
                            ("./x/y/z", "z", "folder"),
                            ("./x/y", "y", "folder"),
                            ("./x", "x", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./x/y/z/test_eggs.py::test_eggs",
                            name="test_eggs",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=adapter_util.fix_relpath(relfile),
                                func=None,
                            ),
                            source=f"{adapter_util.fix_relpath(relfile)}:1",
                            markers=[],
                            parentid="./x/y/z/test_eggs.py",
                        ),
                    ),
                ),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            ("./x/y/z/test_eggs.py", "test_eggs.py", "file"),
                            ("./x/y/z", "z", "folder"),
                            ("./x/y", "y", "folder"),
                            ("./x", "x", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./x/y/z/test_eggs.py::test_eggs.TestSpam",
                            name="test_eggs.TestSpam",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=adapter_util.fix_relpath(relfile),
                                func=None,
                            ),
                            source=f"{adapter_util.fix_relpath(relfile)}:13",
                            markers=[],
                            parentid="./x/y/z/test_eggs.py",
                        ),
                    ),
                ),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            ("./x/y/z/test_eggs.py", "test_eggs.py", "file"),
                            ("./x/y/z", "z", "folder"),
                            ("./x/y", "y", "folder"),
                            ("./x", "x", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./x/y/z/test_eggs.py::test_eggs.TestSpam.TestEggs",
                            name="test_eggs.TestSpam.TestEggs",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=adapter_util.fix_relpath(relfile),
                                func=None,
                            ),
                            source=f"{adapter_util.fix_relpath(relfile)}:28",
                            markers=[],
                            parentid="./x/y/z/test_eggs.py",
                        ),
                    ),
                ),
            ],
        )

    def test_nested_brackets(self):
        stub = util.Stub()
        discovered = StubDiscoveredTests(stub)
        session = StubPytestSession(stub)
        testroot = adapter_util.fix_path("/a/b/c")
        relfile = adapter_util.fix_path("x/y/z/test_eggs.py")
        session.items = [
            create_stub_function_item(
                stub,
                nodeid=f'{relfile}::SpamTests::test_spam[a-[b]-c]',
                name="test_spam[a-[b]-c]",
                originalname="test_spam",
                location=(relfile, 12, "SpamTests.test_spam[a-[b]-c]"),
                fspath=adapter_util.PATH_JOIN(testroot, relfile),
                function=FakeFunc("test_spam"),
            )
        ]

        collector = _discovery.TestCollector(tests=discovered)

        collector.pytest_collection_finish(session)

        self.maxDiff = None
        self.assertEqual(
            stub.calls,
            [
                ("discovered.reset", None, None),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (
                                "./x/y/z/test_eggs.py::SpamTests::test_spam",
                                "test_spam",
                                "function",
                            ),
                            (
                                "./x/y/z/test_eggs.py::SpamTests",
                                "SpamTests",
                                "suite",
                            ),
                            ("./x/y/z/test_eggs.py", "test_eggs.py", "file"),
                            ("./x/y/z", "z", "folder"),
                            ("./x/y", "y", "folder"),
                            ("./x", "x", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./x/y/z/test_eggs.py::SpamTests::test_spam[a-[b]-c]",
                            name="test_spam[a-[b]-c]",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=adapter_util.fix_relpath(relfile),
                                func="SpamTests.test_spam",
                                sub=["[a-[b]-c]"],
                            ),
                            source=f"{adapter_util.fix_relpath(relfile)}:13",
                            markers=None,
                            parentid="./x/y/z/test_eggs.py::SpamTests::test_spam",
                        ),
                    ),
                ),
            ],
        )

    def test_nested_suite(self):
        stub = util.Stub()
        discovered = StubDiscoveredTests(stub)
        session = StubPytestSession(stub)
        testroot = adapter_util.fix_path("/a/b/c")
        relfile = adapter_util.fix_path("x/y/z/test_eggs.py")
        session.items = [
            create_stub_function_item(
                stub,
                nodeid=f'{relfile}::SpamTests::Ham::Eggs::test_spam',
                name="test_spam",
                originalname=None,
                location=(relfile, 12, "SpamTests.Ham.Eggs.test_spam"),
                fspath=adapter_util.PATH_JOIN(testroot, relfile),
                function=FakeFunc("test_spam"),
            )
        ]

        collector = _discovery.TestCollector(tests=discovered)

        collector.pytest_collection_finish(session)

        self.maxDiff = None
        self.assertEqual(
            stub.calls,
            [
                ("discovered.reset", None, None),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (
                                "./x/y/z/test_eggs.py::SpamTests::Ham::Eggs",
                                "Eggs",
                                "suite",
                            ),
                            (
                                "./x/y/z/test_eggs.py::SpamTests::Ham",
                                "Ham",
                                "suite",
                            ),
                            (
                                "./x/y/z/test_eggs.py::SpamTests",
                                "SpamTests",
                                "suite",
                            ),
                            ("./x/y/z/test_eggs.py", "test_eggs.py", "file"),
                            ("./x/y/z", "z", "folder"),
                            ("./x/y", "y", "folder"),
                            ("./x", "x", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./x/y/z/test_eggs.py::SpamTests::Ham::Eggs::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=adapter_util.fix_relpath(relfile),
                                func="SpamTests.Ham.Eggs.test_spam",
                                sub=None,
                            ),
                            source=f"{adapter_util.fix_relpath(relfile)}:13",
                            markers=None,
                            parentid="./x/y/z/test_eggs.py::SpamTests::Ham::Eggs",
                        ),
                    ),
                ),
            ],
        )

    def test_windows(self):
        stub = util.Stub()
        discovered = StubDiscoveredTests(stub)
        session = StubPytestSession(stub)
        testroot = r"C:\A\B\C"
        altroot = testroot.replace("\\", "/")
        relfile = r"X\Y\Z\test_Eggs.py"
        session.items = [
            # typical:
            create_stub_function_item(
                stub,
                # pytest always uses "/" as the path separator in node IDs:
                nodeid="X/Y/Z/test_Eggs.py::SpamTests::test_spam",
                name="test_spam",
                originalname=None,
                # normal path separator (contrast with nodeid):
                location=(relfile, 12, "SpamTests.test_spam"),
                # path separator matches location:
                fspath=testroot + "\\" + relfile,
                function=FakeFunc("test_spam"),
            ),
        ]
        tests = [
            # permutations of path separators
            (r"X/test_a.py", "\\", "\\"),  # typical
            (r"X/test_b.py", "\\", "/"),
            (r"X/test_c.py", "/", "\\"),
            (r"X/test_d.py", "/", "/"),
            (r"X\test_e.py", "\\", "\\"),
            (r"X\test_f.py", "\\", "/"),
            (r"X\test_g.py", "/", "\\"),
            (r"X\test_h.py", "/", "/"),
        ]
        for fileid, locfile, fspath in tests:
            if locfile == "/":
                locfile = fileid.replace("\\", "/")
            elif locfile == "\\":
                locfile = fileid.replace("/", "\\")
            if fspath == "/":
                fspath = f'{testroot}/{fileid}'.replace("\\", "/")
            elif fspath == "\\":
                fspath = f'{testroot}/{fileid}'.replace("/", "\\")
            session.items.append(
                create_stub_function_item(
                    stub,
                    nodeid=f'{fileid}::test_spam',
                    name="test_spam",
                    originalname=None,
                    location=(locfile, 12, "test_spam"),
                    fspath=fspath,
                    function=FakeFunc("test_spam"),
                )
            )

        collector = _discovery.TestCollector(tests=discovered)
        if os.name != "nt":
            collector.parse_item = generate_parse_item("\\")

        collector.pytest_collection_finish(session)

        self.maxDiff = None
        self.assertEqual(
            stub.calls,
            [
                ("discovered.reset", None, None),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (r"./X/Y/Z/test_Eggs.py::SpamTests", "SpamTests", "suite"),
                            (r"./X/Y/Z/test_Eggs.py", "test_Eggs.py", "file"),
                            (r"./X/Y/Z", "Z", "folder"),
                            (r"./X/Y", "Y", "folder"),
                            (r"./X", "X", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id=r"./X/Y/Z/test_Eggs.py::SpamTests::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=testroot,  # not normalized
                                relfile=r".\X\Y\Z\test_Eggs.py",  # not normalized
                                func="SpamTests.test_spam",
                                sub=None,
                            ),
                            source=r".\X\Y\Z\test_Eggs.py:13",  # not normalized
                            markers=None,
                            parentid=r"./X/Y/Z/test_Eggs.py::SpamTests",
                        ),
                    ),
                ),
                # permutations
                # (*all* the IDs use "/")
                # (source path separator should match relfile, not location)
                # /, \, \
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (r"./X/test_a.py", "test_a.py", "file"),
                            (r"./X", "X", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id=r"./X/test_a.py::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=r".\X\test_a.py",
                                func="test_spam",
                                sub=None,
                            ),
                            source=r".\X\test_a.py:13",
                            markers=None,
                            parentid=r"./X/test_a.py",
                        ),
                    ),
                ),
                # /, \, /
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (r"./X/test_b.py", "test_b.py", "file"),
                            (r"./X", "X", "folder"),
                            (".", altroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id=r"./X/test_b.py::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=altroot,
                                relfile=r"./X/test_b.py",
                                func="test_spam",
                                sub=None,
                            ),
                            source=r"./X/test_b.py:13",
                            markers=None,
                            parentid=r"./X/test_b.py",
                        ),
                    ),
                ),
                # /, /, \
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (r"./X/test_c.py", "test_c.py", "file"),
                            (r"./X", "X", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id=r"./X/test_c.py::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=r".\X\test_c.py",
                                func="test_spam",
                                sub=None,
                            ),
                            source=r".\X\test_c.py:13",
                            markers=None,
                            parentid=r"./X/test_c.py",
                        ),
                    ),
                ),
                # /, /, /
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (r"./X/test_d.py", "test_d.py", "file"),
                            (r"./X", "X", "folder"),
                            (".", altroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id=r"./X/test_d.py::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=altroot,
                                relfile=r"./X/test_d.py",
                                func="test_spam",
                                sub=None,
                            ),
                            source=r"./X/test_d.py:13",
                            markers=None,
                            parentid=r"./X/test_d.py",
                        ),
                    ),
                ),
                # \, \, \
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (r"./X/test_e.py", "test_e.py", "file"),
                            (r"./X", "X", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id=r"./X/test_e.py::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=r".\X\test_e.py",
                                func="test_spam",
                                sub=None,
                            ),
                            source=r".\X\test_e.py:13",
                            markers=None,
                            parentid=r"./X/test_e.py",
                        ),
                    ),
                ),
                # \, \, /
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (r"./X/test_f.py", "test_f.py", "file"),
                            (r"./X", "X", "folder"),
                            (".", altroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id=r"./X/test_f.py::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=altroot,
                                relfile=r"./X/test_f.py",
                                func="test_spam",
                                sub=None,
                            ),
                            source=r"./X/test_f.py:13",
                            markers=None,
                            parentid=r"./X/test_f.py",
                        ),
                    ),
                ),
                # \, /, \
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (r"./X/test_g.py", "test_g.py", "file"),
                            (r"./X", "X", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id=r"./X/test_g.py::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=r".\X\test_g.py",
                                func="test_spam",
                                sub=None,
                            ),
                            source=r".\X\test_g.py:13",
                            markers=None,
                            parentid=r"./X/test_g.py",
                        ),
                    ),
                ),
                # \, /, /
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (r"./X/test_h.py", "test_h.py", "file"),
                            (r"./X", "X", "folder"),
                            (".", altroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id=r"./X/test_h.py::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=altroot,
                                relfile=r"./X/test_h.py",
                                func="test_spam",
                                sub=None,
                            ),
                            source=r"./X/test_h.py:13",
                            markers=None,
                            parentid=r"./X/test_h.py",
                        ),
                    ),
                ),
            ],
        )

    def test_mysterious_parens(self):
        stub = util.Stub()
        discovered = StubDiscoveredTests(stub)
        session = StubPytestSession(stub)
        testroot = adapter_util.fix_path("/a/b/c")
        relfile = adapter_util.fix_path("x/y/z/test_eggs.py")
        session.items = [
            create_stub_function_item(
                stub,
                nodeid=f'{relfile}::SpamTests::()::()::test_spam',
                name="test_spam",
                originalname=None,
                location=(relfile, 12, "SpamTests.test_spam"),
                fspath=adapter_util.PATH_JOIN(testroot, relfile),
                function=FakeFunc("test_spam"),
            )
        ]

        collector = _discovery.TestCollector(tests=discovered)

        collector.pytest_collection_finish(session)

        self.maxDiff = None
        self.assertEqual(
            stub.calls,
            [
                ("discovered.reset", None, None),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (
                                "./x/y/z/test_eggs.py::SpamTests",
                                "SpamTests",
                                "suite",
                            ),
                            ("./x/y/z/test_eggs.py", "test_eggs.py", "file"),
                            ("./x/y/z", "z", "folder"),
                            ("./x/y", "y", "folder"),
                            ("./x", "x", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./x/y/z/test_eggs.py::SpamTests::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=adapter_util.fix_relpath(relfile),
                                func="SpamTests.test_spam",
                                sub=[],
                            ),
                            source=f"{adapter_util.fix_relpath(relfile)}:13",
                            markers=None,
                            parentid="./x/y/z/test_eggs.py::SpamTests",
                        ),
                    ),
                ),
            ],
        )

    def test_imported_test(self):
        # pytest will even discover tests that were imported from
        # another module!
        stub = util.Stub()
        discovered = StubDiscoveredTests(stub)
        session = StubPytestSession(stub)
        testroot = adapter_util.fix_path("/a/b/c")
        relfile = adapter_util.fix_path("x/y/z/test_eggs.py")
        srcfile = adapter_util.fix_path("x/y/z/_extern.py")
        session.items = [
            create_stub_function_item(
                stub,
                nodeid=f'{relfile}::SpamTests::test_spam',
                name="test_spam",
                originalname=None,
                location=(srcfile, 12, "SpamTests.test_spam"),
                fspath=adapter_util.PATH_JOIN(testroot, relfile),
                function=FakeFunc("test_spam"),
            ),
            create_stub_function_item(
                stub,
                nodeid=f'{relfile}::test_ham',
                name="test_ham",
                originalname=None,
                location=(srcfile, 3, "test_ham"),
                fspath=adapter_util.PATH_JOIN(testroot, relfile),
                function=FakeFunc("test_spam"),
            ),
        ]

        collector = _discovery.TestCollector(tests=discovered)

        collector.pytest_collection_finish(session)

        self.maxDiff = None
        self.assertEqual(
            stub.calls,
            [
                ("discovered.reset", None, None),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            (
                                "./x/y/z/test_eggs.py::SpamTests",
                                "SpamTests",
                                "suite",
                            ),
                            ("./x/y/z/test_eggs.py", "test_eggs.py", "file"),
                            ("./x/y/z", "z", "folder"),
                            ("./x/y", "y", "folder"),
                            ("./x", "x", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./x/y/z/test_eggs.py::SpamTests::test_spam",
                            name="test_spam",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=adapter_util.fix_relpath(relfile),
                                func="SpamTests.test_spam",
                                sub=None,
                            ),
                            source=f"{adapter_util.fix_relpath(srcfile)}:13",
                            markers=None,
                            parentid="./x/y/z/test_eggs.py::SpamTests",
                        ),
                    ),
                ),
                (
                    "discovered.add_test",
                    None,
                    dict(
                        parents=[
                            ("./x/y/z/test_eggs.py", "test_eggs.py", "file"),
                            ("./x/y/z", "z", "folder"),
                            ("./x/y", "y", "folder"),
                            ("./x", "x", "folder"),
                            (".", testroot, "folder"),
                        ],
                        test=info.SingleTestInfo(
                            id="./x/y/z/test_eggs.py::test_ham",
                            name="test_ham",
                            path=info.SingleTestPath(
                                root=testroot,
                                relfile=adapter_util.fix_relpath(relfile),
                                func="test_ham",
                                sub=None,
                            ),
                            source=f"{adapter_util.fix_relpath(srcfile)}:4",
                            markers=None,
                            parentid="./x/y/z/test_eggs.py",
                        ),
                    ),
                ),
            ],
        )
