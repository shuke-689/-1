# -*- coding: utf-8 -*-
"""把 Edge 的 Default 配置复制到工作区（排除各类缓存），用于启动一个带调试端口的自动化实例。
不修改、不影响用户正在使用的 Edge。
"""
import io
import os
import shutil
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SRC_USER_DATA = r"C:\Users\Administrator\AppData\Local\Microsoft\Edge\User Data"
DST_ROOT = r"C:\Users\Administrator\WorkBuddy\抖音\.edge-work"
DST_USER_DATA = os.path.join(DST_ROOT, "User Data")

# 重目录，全部跳过
SKIP_DIRS = {
    "Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache",
    "DawnWebGPUCache", "GrShaderCache", "ShaderCache", "GraphiteDawnCache",
    "BrowserMetrics", "Crashpad", "component_crx_cache", "extensions_crx_cache",
    "Safe Browsing", "segmentation_platform", "OptimizationGuidePredictionModels",
    "OptimizationHints", "MEIPreload", "OriginTrials", "SSLErrorAssistant",
    "Subresource Filter", "TrustTokenKeyCommitments", "WidevineCdm",
    "Workspaces", "Edge Language Detection Model", "Nurturing", "BrowserMetrics-spare.pma",
    "EADPData Component", "Edge Data Protection Lists", "Edge Notifications",
    "ProvenanceData", "Snapshots", "ZxcvbnData", "hyphen-data", "ActorSafetyLists",
    "AmountExtractionHeuristicRegexes", "CaptchaProviders", "CertificateRevocation",
    "FileTypePolicies", "FirstPartySetsPreloaded", "PKIMetadata", "RecoveryImproved",
    "Real Time Correction", "ScreenAI", "SmartScreen", "Speech Recognition",
    "TpcdMetadata", "hsts_preload", "ThirdPartyModuleList64",
}

# 只复制这些顶层文件（登录态加密密钥就在 Local State 里）
KEEP_ROOT_FILES = {"Local State"}


def main():
    if not os.path.isdir(SRC_USER_DATA):
        print("源目录不存在: %s" % SRC_USER_DATA)
        return 1

    os.makedirs(DST_USER_DATA, exist_ok=True)
    t0 = time.time()
    copied = 0
    skipped = 0

    # 1) 顶层文件
    for name in os.listdir(SRC_USER_DATA):
        sp = os.path.join(SRC_USER_DATA, name)
        dp = os.path.join(DST_USER_DATA, name)
        if os.path.isfile(sp):
            if name in KEEP_ROOT_FILES:
                shutil.copy2(sp, dp)
                copied += 1
            continue

    # 2) 只需要 Default 配置目录
    src_profile = os.path.join(SRC_USER_DATA, "Default")
    dst_profile = os.path.join(DST_USER_DATA, "Default")
    if not os.path.isdir(src_profile):
        print("缺少 Default 配置目录")
        return 1

    os.makedirs(dst_profile, exist_ok=True)
    for root, dirs, files in os.walk(src_profile):
        rel = os.path.relpath(root, src_profile)
        # 顶层跳过缓存目录
        if rel == ".":
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        target_dir = os.path.join(dst_profile, rel)
        os.makedirs(target_dir, exist_ok=True)
        for f in files:
            sf = os.path.join(root, f)
            df = os.path.join(target_dir, f)
            try:
                if os.path.getsize(sf) > 80 * 1024 * 1024:  # 跳过超大文件
                    skipped += 1
                    continue
                shutil.copy2(sf, df)
                copied += 1
            except OSError:
                skipped += 1

    print("复制完成: %d 个文件, 跳过 %d 个, 耗时 %.1fs" % (copied, skipped, time.time() - t0))
    total = sum(os.path.getsize(os.path.join(r, f))
                for r, _, fs in os.walk(DST_USER_DATA) for f in fs)
    print("目标体积: %.1f MB" % (total / 1024 / 1024))
    print("目标路径: %s" % DST_USER_DATA)
    for need in ["Local State", os.path.join("Default", "Network", "Cookies")]:
        p = os.path.join(DST_USER_DATA, need)
        print("  %-30s %s" % (need, "OK" if os.path.exists(p) else "缺失"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
