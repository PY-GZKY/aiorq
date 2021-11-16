#!/usr/bin/env python3
import os
import sys

from aiorq.version import VERSION

git_tag = os.getenv('TRAVIS_TAG')
if git_tag:
    if git_tag.lower().lstrip('v') != str(VERSION).lower():
        print('✖ "TRAVIS_TAG" environment variable does not match aiorq.version: "%s" vs. "%s"' % (git_tag, VERSION))
        sys.exit(1)
    else:
        print('✓ "TRAVIS_TAG" environment variable matches aiorq.version: "%s" vs. "%s"' % (git_tag, VERSION))
else:
    print('✓ "TRAVIS_TAG" not defined')