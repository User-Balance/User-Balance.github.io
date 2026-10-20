// Read-only device inventory. Compile in your CUDA toolkit environment:
// nvcc -O2 nvidia-device-probe.cu -o nvidia-device-probe
#include <cuda_runtime.h>
#include <cstdio>

static bool check(cudaError_t status, const char* operation) {
  if (status == cudaSuccess) return true;
  std::fprintf(stderr, "%s: %s\n", operation, cudaGetErrorString(status));
  return false;
}

int main() {
  int count = 0, driver = 0, runtime = 0;
  if (!check(cudaGetDeviceCount(&count), "cudaGetDeviceCount")) return 1;
  if (!check(cudaDriverGetVersion(&driver), "cudaDriverGetVersion")) return 1;
  if (!check(cudaRuntimeGetVersion(&runtime), "cudaRuntimeGetVersion")) return 1;
  std::printf("CUDA driver API version: %d; runtime: %d; devices: %d\n", driver, runtime, count);
  for (int device = 0; device < count; ++device) {
    cudaDeviceProp p{};
    if (!check(cudaGetDeviceProperties(&p, device), "cudaGetDeviceProperties")) return 1;
    std::printf("\nDevice %d: %s\n", device, p.name);
    std::printf("Compute capability: %d.%d\n", p.major, p.minor);
    std::printf("Visible SM count: %d\n", p.multiProcessorCount);
    std::printf("Warp size: %d threads\n", p.warpSize);
    std::printf("Device memory: %.3f GiB (%zu bytes)\n", double(p.totalGlobalMem)/(1024.0*1024*1024), p.totalGlobalMem);
    std::printf("L2 cache: %.3f MiB (%d bytes)\n", double(p.l2CacheSize)/(1024.0*1024), p.l2CacheSize);
    std::printf("Registers/SM: %d 32-bit entries\n", p.regsPerMultiprocessor);
    std::printf("Shared/SM: %.3f KiB\n", double(p.sharedMemPerMultiprocessor)/1024);
    std::printf("Shared/block default: %.3f KiB\n", double(p.sharedMemPerBlock)/1024);
    std::printf("Shared/block opt-in max: %.3f KiB\n", double(p.sharedMemPerBlockOptin)/1024);
    std::printf("Max threads/SM: %d; max threads/block: %d\n", p.maxThreadsPerMultiProcessor, p.maxThreadsPerBlock);
    std::printf("Max warps/SM by thread slots: %d\n", p.maxThreadsPerMultiProcessor/p.warpSize);
    int max_blocks = 0;
    if (check(cudaDeviceGetAttribute(&max_blocks, cudaDevAttrMaxBlocksPerMultiprocessor, device), "max blocks/SM"))
      std::printf("Max blocks/SM: %d\n", max_blocks);
#if CUDART_VERSION >= 12000
    int cluster = 0;
    if (check(cudaDeviceGetAttribute(&cluster, cudaDevAttrClusterLaunch, device), "cluster launch support"))
      std::printf("Thread-block cluster launch supported: %s\n", cluster ? "yes" : "no");
#endif
  }
  std::puts("\nThis inventory does not measure Tensor Core count, peak FLOPS, actual occupancy or GEMM speed.");
  return 0;
}
