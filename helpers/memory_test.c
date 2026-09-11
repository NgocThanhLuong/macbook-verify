#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    size_t mb = 256;
    if (argc > 1) {
        long v = strtol(argv[1], NULL, 10);
        if (v > 0 && v <= 4096) mb = (size_t)v;
    }
    size_t bytes = mb * 1024ULL * 1024ULL;
    size_t count = bytes / sizeof(uint64_t);
    uint64_t *p = (uint64_t *)malloc(bytes);
    if (!p) {
        fprintf(stderr, "allocation failed for %zu MiB\n", mb);
        return 2;
    }

    const uint64_t a = 0xAAAAAAAAAAAAAAAAULL;
    const uint64_t b = 0x5555555555555555ULL;
    for (size_t i = 0; i < count; ++i) p[i] = a ^ (uint64_t)i;
    for (size_t i = 0; i < count; ++i) {
        uint64_t expected = a ^ (uint64_t)i;
        if (p[i] != expected) {
            fprintf(stderr, "pattern A mismatch at word %zu: got=%016llx expected=%016llx\n",
                    i, (unsigned long long)p[i], (unsigned long long)expected);
            free(p);
            return 3;
        }
        p[i] = b ^ ~(uint64_t)i;
    }
    for (size_t i = 0; i < count; ++i) {
        uint64_t expected = b ^ ~(uint64_t)i;
        if (p[i] != expected) {
            fprintf(stderr, "pattern B mismatch at word %zu: got=%016llx expected=%016llx\n",
                    i, (unsigned long long)p[i], (unsigned long long)expected);
            free(p);
            return 4;
        }
    }
    memset(p, 0, bytes);
    free(p);
    printf("PASS: verified two 64-bit patterns across %zu MiB\n", mb);
    return 0;
}
