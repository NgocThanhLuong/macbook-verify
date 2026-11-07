// MacBook Verify 2.0 — native Metal GPU compute integrity and device metadata.
// Requires Xcode Command Line Tools; no third-party frameworks or privileges.
// Verifies deterministic arithmetic, not hardware provenance or ANE usage.
import Foundation
import Metal

func output(_ json: [String: Any]) {
    if let d = try? JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted, .sortedKeys]),
       let s = String(data: d, encoding: .utf8) {
        print(s)
    }
}
let duration = max(1.0, min(180.0, Double(CommandLine.arguments.dropFirst().first ?? "10") ?? 10))
guard let device = MTLCreateSystemDefaultDevice() else {
    output(["status": "SKIP", "reason": "Metal GPU không khả dụng"])
    exit(0)
}
var details: [String: Any] = [
    "status": "INFO", "gpu_name": device.name,
    "is_low_power": device.isLowPower,
    "has_unified_memory": device.hasUnifiedMemory,
    "is_removable": device.isRemovable,
    "registry_id": String(device.registryID),
    "recommended_max_working_set_bytes": Int64(device.recommendedMaxWorkingSetSize),
    "max_buffer_length_bytes": device.maxBufferLength,
    "max_threads_per_threadgroup": [
        device.maxThreadsPerThreadgroup.width,
        device.maxThreadsPerThreadgroup.height,
        device.maxThreadsPerThreadgroup.depth
    ],
    "ane_executed": false,
    "ane_note": "Metal chạy GPU, không thể coi là bài kiểm tra Neural Engine.",
]
func fail(_ reason: String) -> Never {
    details["status"] = "FAIL"
    details["reason"] = reason
    output(details)
    exit(2)
}
guard let queue = device.makeCommandQueue() else { fail("Không tạo được Metal command queue") }
let length = 65_536
let bytes = length * MemoryLayout<Float>.stride
guard let abuf = device.makeBuffer(length: bytes, options: .storageModeShared),
      let bbuf = device.makeBuffer(length: bytes, options: .storageModeShared),
      let obuf = device.makeBuffer(length: bytes, options: .storageModeShared) else {
    fail("Không cấp phát được GPU buffers")
}
let a = abuf.contents().bindMemory(to: Float.self, capacity: length)
let b = bbuf.contents().bindMemory(to: Float.self, capacity: length)
let o = obuf.contents().bindMemory(to: Float.self, capacity: length)
for i in 0..<length {
    a[i] = Float(i % 997)
    b[i] = Float(i % 991)
    o[i] = -1
}
let source = """
#include <metal_stdlib>
using namespace metal;
kernel void verify(device const float *a [[buffer(0)]],
                   device const float *b [[buffer(1)]],
                   device float *out [[buffer(2)]],
                   uint id [[thread_position_in_grid]]) {
  if (id < 65536) out[id] = a[id] * 3.0f + b[id];
}
"""
let library: MTLLibrary
do {
    library = try device.makeLibrary(source: source, options: nil)
} catch {
    fail("Lỗi biên dịch Metal shader: \(error.localizedDescription)")
}
guard let kernel = library.makeFunction(name: "verify") else {
    fail("Không tìm thấy Metal compute kernel")
}
let pipeline: MTLComputePipelineState
do {
    pipeline = try device.makeComputePipelineState(function: kernel)
} catch {
    fail("Lỗi tạo Metal compute pipeline: \(error.localizedDescription)")
}
let threads = MTLSize(width: min(256, pipeline.maxTotalThreadsPerThreadgroup), height: 1, depth: 1)
let grid = MTLSize(width: length, height: 1, depth: 1)
var completed = 0
var mismatches = 0
let start = ProcessInfo.processInfo.systemUptime
repeat {
    guard let cb = queue.makeCommandBuffer(),
          let enc = cb.makeComputeCommandEncoder() else {
        fail("Không tạo được Metal command buffer / encoder")
    }
    enc.setComputePipelineState(pipeline)
    enc.setBuffer(abuf, offset: 0, index: 0)
    enc.setBuffer(bbuf, offset: 0, index: 1)
    enc.setBuffer(obuf, offset: 0, index: 2)
    enc.dispatchThreads(grid, threadsPerThreadgroup: threads)
    enc.endEncoding()
    cb.commit()
    cb.waitUntilCompleted()
    if cb.status != .completed {
        fail("GPU command buffer lỗi: \(String(describing: cb.error))")
    }
    completed += 1
    // Check ALL 65,536 results on each pass. Values are exact small integers.
    for i in 0..<length {
        let expected = a[i] * 3 + b[i]
        if o[i] != expected {
            mismatches += 1
            if mismatches > 3 { break }
        }
    }
    if mismatches > 0 { fail("Kết quả GPU sai: \(mismatches) phần tử") }
} while ProcessInfo.processInfo.systemUptime - start < duration
let elapsed = max(0.001, ProcessInfo.processInfo.systemUptime - start)
details["status"] = "PASS"
details["test_duration_seconds"] = (elapsed * 100).rounded() / 100
details["passes"] = completed
details["elements_per_pass"] = length
details["total_elements_checked"] = length * completed
details["mismatches"] = mismatches
details["compute_passes_per_second"] = (Double(completed) / elapsed * 100).rounded() / 100
details["method"] = "Metal GPU compute, deterministic float arithmetic, full output verification"
details["warning"] = "Không phải điểm benchmark chuẩn hóa; độ nóng, driver và tác vụ nền ảnh hưởng tốc độ."
output(details)
