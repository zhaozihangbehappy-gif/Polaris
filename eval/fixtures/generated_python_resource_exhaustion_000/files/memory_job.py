"""Memory-limited job with a missing allocator arena cap."""

import os
import resource

MB = 1024 * 1024
LIMIT_MB = 80
ARENA_FRAGMENT_MB = 32
PAYLOAD_MB = 40


def arena_cap_enabled():
    return os.environ.get("MALLOC_ARENA_MAX") in {"1", "2"}


def main():
    resource.setrlimit(resource.RLIMIT_AS, (LIMIT_MB * MB, LIMIT_MB * MB))

    fragments = []
    if not arena_cap_enabled():
        for _ in range(ARENA_FRAGMENT_MB):
            fragments.append(bytearray(MB))

    payload = bytearray(PAYLOAD_MB * MB)
    print(f"processed {len(payload)} bytes")


if __name__ == "__main__":
    main()
