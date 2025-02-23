import textwrap
import unittest

import pytest

from conans.test.utils.tools import TestClient, GenConanfile
from conans.util.files import save


class TransitiveIdsTest(unittest.TestCase):

    def test_transitive_library(self):
        # https://github.com/conan-io/conan/issues/6450
        client = TestClient()
        save(client.cache.new_config_path, "core.package_id:default_unknown_mode=full_version_mode")
        client.save({"conanfile.py": GenConanfile()})
        client.run("create . --name=liba --version=1.0")
        client.run("create . --name=liba --version=1.1")
        client.save({"conanfile.py": GenConanfile().with_require("liba/1.0")})
        client.run("create . --name=libb --version=1.0")
        client.save({"conanfile.py": GenConanfile().with_require("libb/1.0")})
        client.run("create . --name=libc --version=1.0")
        client.save({"conanfile.py": GenConanfile().with_require("libc/1.0")
                                                   .with_require("liba/1.0")})
        client.run("create . --name=libd --version=1.0")
        # The consumer forces to depend on liba/2, instead of liba/1
        client.save({"conanfile.py": GenConanfile().with_require("libc/1.0")
                                                   .with_requirement("liba/1.1", force=True)})
        client.run("create . --name=libd --version=1.0", assert_error=True)
        # both B and C require a new binary
        client.assert_listed_binary(
            {"liba/1.1": ("da39a3ee5e6b4b0d3255bfef95601890afd80709", "Cache"),
             "libb/1.0": ("efdeb15efa0e3e6ce0c9ef9bd82c56e4b2188c8a", "Missing"),
             "libc/1.0": ("fea281081e89fcc36242a68b0dbb16276a84f624", "Missing"),
             "libd/1.0": ("13a3ed814d78c8b91f303db7d4cdd7c4e614323c", "Build")
             })

    def test_transitive_major_mode(self):
        # https://github.com/conan-io/conan/issues/6450
        # Test LibE->LibD->LibC->LibB->LibA
        # LibC declares that it only depends on major version changes of its upstream
        # So LibC package ID doesn't change, even if LibA changes
        # But LibD package ID changes, even if its direct dependency LibC doesn't
        client = TestClient()
        save(client.cache.new_config_path, "core.package_id:default_unknown_mode=full_version_mode")
        # LibA
        client.save({"conanfile.py": GenConanfile()})
        client.run("create . --name=liba --version=1.0")
        client.run("create . --name=liba --version=1.1")
        # libB -> LibA
        client.save({"conanfile.py": GenConanfile().with_require("liba/1.0")})
        client.run("create . --name=libb --version=1.0")
        # libC -> libB
        major_mode = "self.info.requires.major_mode()"
        client.save({"conanfile.py": GenConanfile().with_require("libb/1.0")
                                                   .with_package_id(major_mode)})
        client.run("create . --name=libc --version=1.0")
        # Check the LibC ref with RREV keeps the same
        client.assert_listed_binary({"libc/1.0": ("2aa3bb6726dfc6c825a91f3b465b769e770ee902",
                                                  "Build")})
        # LibD -> LibC
        client.save({"conanfile.py": GenConanfile().with_require("libc/1.0")})
        client.run("create . --name=libd --version=1.0")
        # LibE -> LibD, LibA/2.0
        client.save({"conanfile.py": GenConanfile().with_require("libd/1.0")
                                                   .with_requirement("liba/1.1", force=True)})
        client.run("create . --name=libe --version=1.0", assert_error=True)
        # Check the LibC ref with RREV keeps the same, it is in cache, not missing
        # But LibD package ID changes and is missing, because it depends transitively on LibA
        client.assert_listed_binary(
            {"liba/1.1": ("da39a3ee5e6b4b0d3255bfef95601890afd80709", "Cache"),
             "libb/1.0": ("efdeb15efa0e3e6ce0c9ef9bd82c56e4b2188c8a", "Missing"),
             "libc/1.0": ("2aa3bb6726dfc6c825a91f3b465b769e770ee902", "Cache"),
             "libd/1.0": ("13a3ed814d78c8b91f303db7d4cdd7c4e614323c", "Missing"),
             "libe/1.0": ("f93a37dd8bc53991d7485235c6b3e448942c52ff", "Build")
             })

    @pytest.mark.xfail(reason="package_id have changed")
    def test_transitive_unrelated(self):
        # https://github.com/conan-io/conan/issues/6450
        client = TestClient()
        # LibA
        client.save({"conanfile.py": GenConanfile()})
        client.run("create . --name=liba --version=1.0")
        client.run("create . --name=liba --version=2.0")
        # libB -> LibA
        client.save({"conanfile.py": GenConanfile().with_require("liba/1.0")})
        client.run("create . --name=libb --version=1.0")
        # libC -> libB
        unrelated = "self.info.requires['libb'].unrelated_mode()"
        client.save({"conanfile.py": GenConanfile().with_require("libb/1.0")
                    .with_package_id(unrelated)})
        client.run("create . --name=libc --version=1.0")
        # LibD -> LibC
        client.save({"conanfile.py": GenConanfile().with_require("libc/1.0")})
        client.run("create . --name=libd --version=1.0")
        # LibE -> LibD, LibA/2.0
        client.save({"conanfile.py": GenConanfile().with_require("libd/1.0")
                    .with_require("liba/2.0")})
        client.run("create . --name=libe --version=1.0", assert_error=True)
        self.assertIn("liba/2.0:5ab84d6acfe1f23c4fae0ab88f26e3a396351ac9 - Cache", client.out)
        self.assertIn("libb/1.0:e71235a6f57633221a2b85f9b6aca14cda69e1fd - Missing", client.out)
        self.assertIn("libc/1.0:e3884c6976eb7debb8ec57aada7c0c2beaabe8ac - Missing", client.out)
        self.assertIn("libd/1.0:9b0b7b0905c9bc2cb9b7329f842b3b7c6663e8c3 - Missing", client.out)

    @pytest.mark.xfail(reason="package_id have changed")
    def test_transitive_second_level_header_only(self):
        # https://github.com/conan-io/conan/issues/6450
        client = TestClient()
        # LibA
        client.save({"conanfile.py": GenConanfile()})
        client.run("create . --name=liba --version=1.0")
        client.run("create . --name=liba --version=2.0")
        # libB -> LibA
        client.save({"conanfile.py": GenConanfile().with_require("liba/1.0")})
        client.run("create . --name=libb --version=1.0")
        # libC -> libB

        unrelated = "self.info.clear()"
        client.save({"conanfile.py": GenConanfile().with_require("libb/1.0")
                                                   .with_package_id(unrelated)})
        client.run("create . --name=libc --version=1.0")
        # LibD -> LibC
        client.save({"conanfile.py": GenConanfile().with_require("libc/1.0")})
        client.run("create . --name=libd --version=1.0")
        self.assertIn("libc/1.0:5ab84d6acfe1f23c4fae0ab88f26e3a396351ac9 - Cache", client.out)

        # LibE -> LibD, LibA/2.0
        client.save({"conanfile.py": GenConanfile().with_require("libd/1.0")
                                                   .with_require("liba/2.0")})
        client.run("create . --name=libe --version=1.0", assert_error=True)  # LibD is NOT missing!
        self.assertIn("libd/1.0:119e0b2903330cef59977f8976cb82a665b510c1 - Cache", client.out)
        # USE THE NEW FIXED PACKAGE_ID
        client.run("create . --name=libe --version=1.0", assert_error=True)
        self.assertIn("liba/2.0:5ab84d6acfe1f23c4fae0ab88f26e3a396351ac9 - Cache", client.out)
        self.assertIn("libb/1.0:e71235a6f57633221a2b85f9b6aca14cda69e1fd - Missing", client.out)
        self.assertIn("libc/1.0:5ab84d6acfe1f23c4fae0ab88f26e3a396351ac9 - Cache", client.out)
        self.assertIn("libd/1.0:95b14a919aa70f9a7e24afbf48d1101cff344a67 - Missing", client.out)

    def test_transitive_header_only(self):
        # https://github.com/conan-io/conan/issues/6450
        client = TestClient()
        save(client.cache.new_config_path, "core.package_id:default_unknown_mode=full_version_mode")
        client.save({"conanfile.py": GenConanfile()})
        client.run("create . --name=liba --version=1.0")
        client.run("create . --name=liba --version=2.0")
        client.save({"conanfile.py": GenConanfile().with_require("liba/1.0")
                                                   .with_package_id("self.info.clear()")})
        client.run("create . --name=libb --version=1.0")
        client.save({"conanfile.py": GenConanfile().with_require("libb/1.0")})
        client.run("create . --name=libc --version=1.0")
        client.save({"conanfile.py": GenConanfile().with_require("libc/1.0")
                                                   .with_require("liba/1.0")})
        client.run("create . --name=libd --version=1.0")
        client.save({"conanfile.py": GenConanfile().with_require("libc/1.0")
                                                   .with_requirement("liba/2.0", force=True)})
        # USE THE NEW FIXED PACKAGE_ID
        client.run("create . --name=libd --version=1.0", assert_error=True)
        client.assert_listed_binary({"liba/2.0": ("da39a3ee5e6b4b0d3255bfef95601890afd80709", "Cache"),
                                     "libb/1.0": ("da39a3ee5e6b4b0d3255bfef95601890afd80709", "Cache"),
                                     "libc/1.0": ("2d7000cf800f37e01880897faf74a366a21bebdc", "Missing"),
                                     })
