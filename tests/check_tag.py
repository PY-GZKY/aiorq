#!/usr/bin/env python3
import os
import sys

from aiorq.version import __version__

git_tag = os.getenv('TRAVIS_TAG')
if git_tag:
    if git_tag.lower().lstrip('v') != str(__version__).lower():
        print('✖ "TRAVIS_TAG" environment variable does not match aiorq.version: "%s" vs. "%s"' % (git_tag, __version__))
        sys.exit(1)
    else:
        print('✓ "TRAVIS_TAG" environment variable matches aiorq.version: "%s" vs. "%s"' % (git_tag, __version__))
else:
    print('✓ "TRAVIS_TAG" not defined')
