/*
 * MacBook Verify 2.0 — multi-pattern allocated RAM integrity check.
 * Uses only a bounded user-space allocation; cannot scan reserved RAM or
 * prove the absence of all intermittent/SoC memory faults.
 * No root privileges, no firmware interfaces.
 */
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static uint64_t mix64(uint64_t x) {
    x += UINT64_C(0x9e3779b97f4a7c15);
    x = (x ^ (x >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
    x = (x ^ (x >> 27)) * UINT64_C(0x94d049bb133111eb);
    return x ^ (x >> 31);
}
static int verify(volatile uint64_t *p, size_t count, int pass) {
    const uint64_t a = UINT64_C(0xaaaaaaaaaaaaaaaa);
    const uint64_t b = UINT64_C(0x5555555555555555);
    for (size_t i=0; i<count; ++i) {
        uint64_t expected;
        switch (pass) {
            case 0: expected=a ^ (uint64_t)i; break;
            case 1: expected=b ^ ~(uint64_t)i; break;
            case 2: expected=(i & 1) ? a : b; break;
            case 3: expected=mix64((uint64_t)i ^ UINT64_C(0xcafe2026beef1234)); break;
            default: return 2;
        }
        if (p[i] != expected) {
            fprintf(stderr,"FAIL pass=%d word=%zu got=%016" PRIx64 " expected=%016" PRIx64 "\n",
                    pass, i, p[i], expected);
            return 3;
        }
    }
    return 0;
}
int main(int argc, char **argv) {
    unsigned long long mb=256;
    if (argc>1) {
        char *end=NULL;
        errno=0;
        mb=strtoull(argv[1],&end,10);
        if (errno || !end || *end || mb<1 || mb>8192) {
            fprintf(stderr,"RAM MiB must be 1..8192\n");
            return 2;
        }
    }
    if (mb>(SIZE_MAX/(1024ULL*1024ULL))) return 2;
    size_t size=(size_t)mb*1024ULL*1024ULL;
    size_t count=size/sizeof(uint64_t);
    volatile uint64_t *p=(volatile uint64_t*)malloc(size);
    if (!p) {
        fprintf(stderr,"SKIP allocation failed for %llu MiB\n",mb);
        return 77;
    }
    struct timespec start;
    clock_gettime(CLOCK_MONOTONIC,&start);
    const uint64_t a=UINT64_C(0xaaaaaaaaaaaaaaaa);
    const uint64_t b=UINT64_C(0x5555555555555555);
    for (int pass=0; pass<4; ++pass) {
        for (size_t i=0; i<count; ++i) {
            switch (pass) {
                case 0: p[i]=a ^ (uint64_t)i; break;
                case 1: p[i]=b ^ ~(uint64_t)i; break;
                case 2: p[i]=(i&1)?a:b; break;
                case 3: p[i]=mix64((uint64_t)i ^ UINT64_C(0xcafe2026beef1234)); break;
            }
        }
        if (verify(p,count,pass)!=0) {
            free((void*)p);
            return 3;
        }
        printf("PASS pattern=%d verified=%llu MiB\n",pass,mb);
        fflush(stdout);
    }
    struct timespec end;
    clock_gettime(CLOCK_MONOTONIC,&end);
    double elapsed=(end.tv_sec-start.tv_sec)+(end.tv_nsec-start.tv_nsec)/1e9;
    memset((void*)p,0,size);
    free((void*)p);
    printf("PASS: 4 memory patterns x %llu MiB in %.2f seconds; 0 mismatches\n",mb,elapsed);
    return 0;
}
