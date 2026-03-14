# Tests package — makes the local tests/ directory a proper Python package,
# which ensures it takes precedence over any installed 'tests' package in
# site-packages when running pytest with pythonpath = ["src", "."].
