#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from update_price import USD2RialsUpdater

if __name__ == '__main__':
    updater = USD2RialsUpdater()
    ok = updater.run()
    print('Result:', ok)