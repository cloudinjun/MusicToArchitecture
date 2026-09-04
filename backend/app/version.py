"""The compiler's own version, carried into every run identity.

Bump the minor when a change alters what gets built from the same score -- new
emitters, changed layout rules, resized plates. Bump the patch for changes that leave
the geometry alone. The four selection outcomes travel in the identity beside this, so
most behavioural drift changes the identity even when nobody remembered to bump; the
constant exists for the drift they cannot catch, and a stale value here costs an
overwritten artifact directory, which is precisely the bug the identity exists to end.
"""

COMPILER_VERSION = '3.2.0'
