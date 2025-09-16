import numpy as np
import pandas as pd
from pathlib import Path
from osgeo import gdal
from collections import defaultdict

# 启用异常处理
gdal.UseExceptions()

def search_tif(source_path: str) -> list[str]:
    """
    递归搜索指定路径下所有 .tif 和 .tiff 文件（返回字符串格式路径，兼容gdal）
    参数：
        source_path: 源文件夹路径（字符串）
    返回：
        所有TIF文件的绝对路径列表（字符串）
    """
    """递归搜索TIF文件，先校验路径合法性"""
    # 1. 转换为Path对象，便于后续操作（新增异常捕获）
    try:
        source_dir = Path(source_path).absolute()  # 转为绝对路径，避免相对路径歧义
    except Exception as e:
        raise ValueError(f"[错误] 路径格式非法：{source_path}\n错误原因：{str(e)}（可能包含特殊字符或无效符号）") from e

    # 2. 校验路径是否存在（原有逻辑保留）
    if not source_dir.exists():
        raise ValueError(
            f"【路径不存在】输入的影像文件夹路径不存在：{source_dir}\n"
            "请检查：① 路径是否拼写正确；② 文件是否被移动/删除"
        )

    # 3. 校验路径是否为文件夹（而非文件）（原有逻辑保留）
    if not source_dir.is_dir():
        raise ValueError(
            f"【路径类型错误】输入的路径是文件而非文件夹：{source_dir}\n"
            "请传入影像所在的文件夹路径（如D:\\JM\\lzy\\test_data2），而非单个文件路径"
        )

    # 4. 校验是否有目录访问权限（避免Windows/Linux权限不足）（原有逻辑保留）
    try:
        # 尝试列出目录内1个文件，验证权限
        next(source_dir.iterdir(), None)  # 无文件时返回None，不报错
    except PermissionError:
        raise PermissionError(
            f"【权限不足】无访问文件夹 {source_dir} 的权限\n"
            "请检查：① Windows：右键文件夹→属性→安全→添加当前用户的读写权限；② Linux：chmod +rwx 目录路径"
        )

    # 5. 正常搜索TIF文件（新增子文件夹搜索权限异常捕获）
    try:
        tif_files = [str(file) for file in source_dir.rglob("*.tif")]
        tiff_files = [str(file) for file in source_dir.rglob("*.tiff")]
    except PermissionError as e:
        raise PermissionError(
            f"【权限不足】搜索子文件夹时被拒绝：{str(e)}\n"
            "请检查子文件夹的访问权限（如Windows子文件夹安全设置、Linux文件权限）"
        ) from e
    except Exception as e:
        raise RuntimeError(f"【搜索错误】递归搜索TIF文件时出错：{str(e)}") from e

    all_tif = tiff_files + tif_files

    # 6. 若未找到TIF，给出明确提示（而非静默处理）（原有逻辑保留）
    if not all_tif:
        raise FileNotFoundError(
            f"【无TIF文件】在文件夹 {source_dir} 及其子文件夹中未找到任何 .tif 或 .tiff 文件\n"
            "请检查：① 影像文件是否放在该文件夹下；② 文件后缀是否为 .tif/.tiff（注意区分大小写，如.TIF需改为.tif）"
        )

    print(f"【搜索成功】找到 {len(all_tif)} 个TIF文件：{all_tif}")
    return all_tif


def get_tif_id(tif_name: str, sate_type: str) -> str:
    """
    根据卫星类型提取影像ID（严格保留原始业务逻辑）
    参数：
        tif_name: 不带后缀的影像文件名（如 "GF1_20230101_xxx"）
        sate_type: 卫星类型（如 "GF1", "zy3"）
    返回：
        影像ID（用于分组），异常时返回原文件名
    """

    # 新增：参数类型校验
    if not isinstance(tif_name, str):
        raise TypeError(f"[错误] tif_name 必须是字符串类型，当前为 {type(tif_name).__name__}")
    if not isinstance(sate_type, str):
        raise TypeError(f"[错误] sate_type 必须是字符串类型，当前为 {type(sate_type).__name__}")
    # 新增：空字符串校验
    if not tif_name.strip():
        raise ValueError("[错误] tif_name 不能为空字符串")
    if not sate_type.strip():
        raise ValueError("[错误] sate_type 不能为空字符串")

    parts = tif_name.split("_")  # 预分割，减少重复计算
    try:
        if sate_type in ("GF1", "GF2", "GF6", "ZY1"):
            return tif_name.split("_")[-1].split("-")[0]  # 等价于原逻辑的 split('_')[-1].split('-')[0]
        elif sate_type == "GF7":
            return parts[-1]
        elif sate_type in ("zy303a","zy302a"):
            return f"{parts[2]}_{parts[3]}"
        elif sate_type in ("SV1-03", "SV-2"):
            return parts[2]
        elif sate_type in ("TH01-01","TH01-02","TH01-03","TH01-04"):
            return f"{parts[-2]}_{parts[-1]}"
        else:
            return tif_name  # 未知卫星类型，返回原文件名避免分组失败
    except IndexError:
        # 文件名格式异常时，返回原文件名
        print(f"[警告] 文件名 {tif_name} 格式异常，用原文件名作为ID")
        return tif_name


def preprocess_tif(tif_names: list[str]) -> tuple[list[str], list[list[str]], list[list[str]]]:
    """
    预处理TIF文件：按「卫星类型→影像ID」二级分组（保留原始分组逻辑）
    参数：
        tif_names: 单张/多张TIF文件路径列表（search_tif返回值或单文件列表）
    返回：
        tif_satetypes: 分组对应的卫星类型列表（与分组一一对应）
        tifs: 分组后的影像名称列表（每个元素是同一ID的影像名称集合）
        tifs_path: 分组后的影像路径列表（每个元素是同一ID的影像路径集合）
    """

    # 新增：参数类型校验
    if not isinstance(tif_names, list):
        raise TypeError(f"[错误] tif_names 必须是列表类型，当前为 {type(tif_names).__name__}")
    for idx, path in enumerate(tif_names):
        if not isinstance(path, str):
            raise TypeError(f"[错误] tif_names 列表中第{idx + 1}个元素必须是字符串路径，当前为 {type(path).__name__}")
        if not Path(path).exists():
            raise FileNotFoundError(f"[错误] tif_names 列表中第{idx + 1}个路径不存在：{path}")

    # 第一步：提取每个TIF的核心信息（卫星类型、文件名、路径）
    tif_info = []
    for tif_path in tif_names:
        path_obj = Path(tif_path)
        tif_name = path_obj.stem  # 不带后缀的文件名（如 "GF1_20230101_xxx"）
        sate_type = tif_name.split("_")[0]  # 卫星类型：按"_"分割，取第一部分
        tif_info.append((sate_type, tif_name, tif_path))

    # 第二步：按「卫星类型→影像ID」二级分组（用defaultdict简化逻辑）
    # 一级键：卫星类型；二级键：影像ID；值：(tif_name, tif_path)列表
    group_dict = defaultdict(lambda: defaultdict(list))
    for sate_type, tif_name, tif_path in tif_info:
        tif_id = get_tif_id(tif_name, sate_type)
        group_dict[sate_type][tif_id].append((tif_name, tif_path))

    # 第三步：整理分组结果（匹配原始返回格式）
    tif_satetypes = []
    tifs = []
    tifs_path = []
    for sate_type, id_groups in group_dict.items():
        for tif_id, id_group in id_groups.items():
            # 提取同一ID下的所有影像名称和路径
            group_names = [item[0] for item in id_group]
            group_paths = [item[1] for item in id_group]
            tif_satetypes.append(sate_type)
            tifs.append(group_names)
            tifs_path.append(group_paths)

    return tif_satetypes, tifs, tifs_path


def get_message(tif_name: str, sate_type: str) -> list:
    """
    提取单张影像的元信息（影像型号、时相、传感器等，严格保留原始逻辑）
    参数：
        tif_name: 不带后缀的影像文件名
        sate_type: 卫星类型
    返回：
        元信息列表（顺序：影像型号、卫星类型、影像时相、传感器类型、传感器角度、分辨率）
    """
    # 初始化默认值（避免None导致CSV空值，用空字符串占位）
    tif_id = tif_name
    sate_type_ret = tif_name.split("_")[0] # 卫星类型：取文件名第一个下划线前的完整部分（还原原始逻辑）
    tif_time = ""
    sensor_type = ""
    sensor_angle = "-"  # 无角度信息默认用"-"
    resolution = ""
    parts = tif_name.split("_")  # 预分割，减少重复计算

    try:
        if sate_type == "GF1":
            tif_time = parts[4]
            sensor_prefix = tif_name.split("-")[-1][0]
            if sensor_prefix == "M":
                sensor_type = "多光谱"
                resolution = "8m"
            elif sensor_prefix == "P":
                sensor_type = "全色"
                resolution = "2m"

        elif sate_type == "GF2":
            tif_time = parts[4]
            sensor_prefix = tif_name.split("-")[-1][0]
            if sensor_prefix == "M":
                sensor_type = "多光谱"
                resolution = "4m"
            elif sensor_prefix == "P":
                sensor_type = "全色"
                resolution = "1m"

        elif sate_type == "GF6":
            tif_time = parts[4]
            sensor_prefix = tif_name.split("-")[-1][0]
            if sensor_prefix == "M":
                sensor_type = "多光谱"
                resolution = "8m"
            elif sensor_prefix == "P":
                sensor_type = "全色"
                resolution = "2m"

        elif sate_type == "GF7":
            tif_time = parts[4][:8]  # 时间取前8位（YYYYMMDD）
            sensor_prefix = parts[5][0]
            if sensor_prefix == "M":
                sensor_type = "多光谱"
                sensor_angle = "后视"
                resolution = "3.2m"
            elif sensor_prefix == "B":
                sensor_type = "全色"
                sensor_angle = "后视"
                resolution = "0.8m"
            elif sensor_prefix == "F":
                sensor_type = "全色"
                sensor_angle = "前视"
                resolution = "0.8m"

        elif sate_type in ("zy303a","zy302a"):
            tif_time = parts[4][:8]
            sensor_prefix = parts[1][0]
            if sensor_prefix == "b":
                sensor_type = "全色"
                sensor_angle = "后视"
                resolution = "3m"
            elif sensor_prefix == "f":
                sensor_type = "全色"
                sensor_angle = "前视"
                resolution = "3m"
            elif sensor_prefix == "n":
                sensor_type = "全色"
                sensor_angle = "下视"
                resolution = "2m"
            elif sensor_prefix == "m":
                sensor_type = "多光谱"
                sensor_angle = "下视"
                resolution = "8m"

        elif sate_type == "ZY1":
            tif_time = parts[4]
            sensor_prefix = tif_name.split("-")[-1][0]
            if sensor_prefix == "M":
                sensor_type = "多光谱"
                resolution = "10m"
            elif sensor_prefix == "P":
                sensor_type = "全色"
                resolution = "2.5m"

        elif sate_type == "SV1-03":
            tif_time = parts[1]
            sensor_prefix = tif_name.split("-")[-1][0]
            if sensor_prefix == "M":
                sensor_type = "多光谱"
                resolution = "2m"
            elif sensor_prefix == "P":
                sensor_type = "全色"
                resolution = "0.5m"

        elif sate_type == "SV-2":
            tif_time = parts[1]
            sensor_prefix = tif_name.split("-")[-1][0]
            if sensor_prefix == "M":
                sensor_type = "多光谱"
                resolution = "2m"
            elif sensor_prefix == "P":
                sensor_type = "全色"
                resolution = "0.5m"

        elif sate_type in ("TH01-01","TH01-02","TH01-03","TH01-04"):
            tif_time = parts[1][1:9]  # 时间取第2-9位（如 "T20230101" → "20230101"）
            sensor_prefix = parts[3][0]
            angle = parts[4]
            if sensor_prefix == "S" and angle == "1":
                sensor_type = "全色"
                sensor_angle = "前视"
                resolution = "5m"
            elif sensor_prefix == "S" and angle == "2":
                sensor_type = "全色"
                sensor_angle = "下视"
                resolution = "5m"
            elif sensor_prefix == "S" and angle == "3":
                sensor_type = "全色"
                sensor_angle = "后视"
                resolution = "5m"
            elif sensor_prefix == "G":
                sensor_type = "高分辨"
                sensor_angle = "下视"
                resolution = "2m"
            elif sensor_prefix == "D":
                sensor_type = "多光谱"
                sensor_angle = "下视"
                resolution = "8m"

    except IndexError:
        # 文件名格式异常时，返回默认值（避免程序崩溃）
        print(f"[警告] 文件名 {tif_name} 格式异常，元信息提取不完整")

    return [tif_id, sate_type_ret, tif_time, sensor_type, sensor_angle, resolution]


def get_quality(source_path: str, tif_path: str) -> list[bool]:
    """
    评估单张影像的质量（可打开性、完整性、RPC文件存在性，保留原始逻辑）
    参数：
        source_path: 源文件夹路径（用于搜索RPC文件）
        tif_path: 影像文件路径
    返回：
        质量评估列表（顺序：是否能打开、是否损坏、光谱是否缺失、是否存在RPC）
    """
    is_open = False  # 影像是否能正常打开
    is_bad = False  # 影像是否损坏（0值像素占比>30%）
    is_loss = False  # 光谱是否缺失（波段数<1）
    exist_rpc = False  # 是否存在对应的RPC文件
    data = None  # 初始化GDAL数据集，用于后续关闭

    # 1. 评估影像可打开性和完整性
    try:
        data = gdal.Open(tif_path)
        if data is not None:
            is_open = True
            try:
                # 获取影像尺寸
                x_size = data.RasterXSize
                y_size = data.RasterYSize
                band_count = data.RasterCount

                # 定义块大小（根据内存调整，如512x512）
                block_size = 512
                total_bad = 0
                total_pixels = 0

                # 分块遍历影像
                for y in range(0, y_size, block_size):
                    # 计算当前块的实际高度（最后一块可能不足block_size）
                    current_y_size = min(block_size, y_size - y)
                    for x in range(0, x_size, block_size):
                        current_x_size = min(block_size, x_size - x)

                        # 分块读取数据（仅读取当前块）
                        data_block = data.ReadAsArray(x, y, current_x_size, current_y_size)
                        if data_block is None:
                            raise ValueError(f"读取块({x},{y})失败")

                        # 累加坏像素和总像素数
                        block_bad = np.sum(data_block == 0)
                        block_total = np.prod(data_block.shape)
                        total_bad += block_bad
                        total_pixels += block_total

                # 计算坏像素比例（避免除零）
                is_bad = (total_bad / total_pixels) > 0.3 if total_pixels > 0 else False
                # 光谱缺失判断（只要有1个波段即不缺失）
                is_loss = band_count < 1
            except Exception as e:
                # 读取数据失败视为「光谱缺失」
                is_loss = True
                print(f"[警告] 读取影像 {Path(tif_path).name} 失败：{str(e)}")
        else:
            print(f"[警告] 影像 {Path(tif_path).name} 无法打开")
    except Exception as e:
        # 新增：捕获GDAL打开文件时的意外异常（如文件被占用、格式错误）
        print(f"[错误] 处理影像 {Path(tif_path).name} 时出错：{str(e)}")
        is_loss = True  # 标记为光谱缺失
    finally:
        # 新增：显式关闭GDAL数据集，释放资源
        if data is not None:
            del data  # GDAL数据集无close()，通过del释放

    # 2. 检查RPC文件（两种格式：{影像名}.rpc 或 {影像名}_rpc.txt，保留原始打印）
    tif_stem = Path(tif_path).stem
    source_dir = Path(source_path)
    rpc_files = []
    rpb_files = []  # 新增rpb文件列表
    try:
        # 搜索所有可能的RPC文件
        rpc_files = list(source_dir.rglob("*.rpc")) + list(source_dir.rglob("*_rpc.txt"))
        rpb_files = list(source_dir.rglob("*.rpb"))  # 新增rpb文件搜索
    except PermissionError as e:
        print(f"[警告] 搜索RPC文件时权限不足：{str(e)}")

    # 优化点1：仅在有RPC文件时才检查，无RPC文件直接提示
    if not rpc_files:
        print(f"[RPC匹配] 影像 {tif_stem}：未找到任何RPC文件")
    else:
        # 优化点2：遍历RPC文件，只打印匹配成功的日志，找到后立即退出
        for rpc_file in rpc_files:
            rpc_stem = rpc_file.stem
            # 匹配规则：RPC文件名与影像名完全一致，或RPC名=影像名+"_rpc"
            if rpc_stem == tif_stem or rpc_stem == f"{tif_stem}_rpc":
                exist_rpc = True
                print(f"[RPC匹配成功] 影像 {tif_stem} 找到对应RPC文件：{rpc_file.name}")
                break  # 找到匹配后立即停止检查
        # 优化点3：所有RPC文件都不匹配时，只打印一条总结日志
        if not exist_rpc:
            print(f"[RPC匹配失败] 影像 {tif_stem}：未找到匹配的RPC文件（共搜索到{len(rpc_files)}个RPC文件）")

    # 新增：检查RPB文件
    exist_rpb = False  # 新增rpb存在标记
    if not rpb_files:
        print(f"[RPB匹配] 影像 {tif_stem}：未找到任何RPB文件")
    else:
        for rpb_file in rpb_files:
            rpb_stem = rpb_file.stem
            if rpb_stem == tif_stem or rpb_stem == f"{tif_stem}_rpb":
                exist_rpb = True
                print(f"[RPB匹配成功] 影像 {tif_stem} 找到对应RPB文件：{rpb_file.name}")
                break
        if not exist_rpb:
            print(f"[RPB匹配失败] 影像 {tif_stem}：未找到匹配的RPB文件（共搜索到{len(rpb_files)}个RPB文件）")

    return [is_open, is_bad, is_loss, exist_rpc,exist_rpb]


def get_tif(tifs: list[str], tifs_path: list[str], tif_type: str, source_path: str) -> np.ndarray:
    """
    处理单组影像（同一ID）：合并元信息和质量信息（保留原始逻辑）
    参数：
        tifs: 单组影像的名称列表
        tifs_path: 单组影像的路径列表
        tif_type: 该组影像的卫星类型
        source_path: 源文件夹路径
    返回：
        该组影像的完整信息数组（每行对应一张影像）
    """
    tifs_message = []
    for tif_name, tif_path in zip(tifs, tifs_path):
        # 提取元信息和质量信息
        meta_msg = get_message(tif_name, tif_type)
        quality_msg = get_quality(source_path, tif_path)
        # 合并信息（添加云占比字段，原始逻辑为"-"）
        full_msg = meta_msg + quality_msg + ["-"]
        tifs_message.append(full_msg)

    # 转为numpy数组（匹配原始返回格式）
    return np.array(tifs_message) if tifs_message else np.array([])


def get_lack(tif_message: np.ndarray, tif_type: str) -> np.ndarray:
    """
    判断单组影像（同一ID）缺失的传感器类型（严格保留原始业务逻辑）
    参数：
        tif_message: 单组影像的完整信息数组（get_tif返回值）
        tif_type: 该组影像的卫星类型
    返回：
        缺失信息数组（每行对应一条缺失记录）
    """
    if tif_message.size == 0:
        return np.array([])  # 空数组，避免后续vstack报错

    lack_list = []
    # 提取该组核心信息（原始逻辑：取第1行的ID，所有行的传感器类型和角度）
    tifs_id = tif_message[0, 0]
    sensor_types = tif_message[:, 3]  # 传感器类型（第4列，0索引）
    sensor_angles = tif_message[:, 4]  # 传感器角度（第5列，0索引）

    if tif_type == "GF1":
        if np.sum(sensor_types == "全色") == 0:
            lack_list.append([tifs_id, "全色", "-", "2m"])
        if np.sum(sensor_types == "多光谱") == 0:
            lack_list.append([tifs_id, "多光谱", "-", "8m"])

    elif tif_type == "GF2":
        if np.sum(sensor_types == "全色") == 0:
            lack_list.append([tifs_id, "全色", "-", "1m"])
        if np.sum(sensor_types == "多光谱") == 0:
            lack_list.append([tifs_id, "多光谱", "-", "4m"])

    elif tif_type == "GF6":
        if np.sum(sensor_types == "全色") == 0:
            lack_list.append([tifs_id, "全色", "-", "2m"])
        if np.sum(sensor_types == "多光谱") == 0:
            lack_list.append([tifs_id, "多光谱", "-", "8m"])

    elif tif_type == "GF7":
        # 检查「全色-后视」「全色-前视」「多光谱-后视」
        has_p_back = np.sum((sensor_types == "全色") & (sensor_angles == "后视")) == 0
        has_p_front = np.sum((sensor_types == "全色") & (sensor_angles == "前视")) == 0
        if has_p_back:
            lack_list.append([tifs_id, "全色", "后视", "0.8m"])
        if has_p_front:
            lack_list.append([tifs_id, "全色", "前视", "0.8m"])
        if np.sum(sensor_types == "多光谱") == 0:
            lack_list.append([tifs_id, "多光谱", "后视", "3.2m"])

    elif tif_type in ("zy303a","zy302a"):
        # 原始逻辑：下视缺失时填"前视"，此处保留
        has_p_back = np.sum((sensor_types == "全色") & (sensor_angles == "后视")) == 0
        has_p_front = np.sum((sensor_types == "全色") & (sensor_angles == "前视")) == 0
        has_p_down = np.sum((sensor_types == "全色") & (sensor_angles == "下视")) == 0
        if has_p_back:
            lack_list.append([tifs_id, "全色", "后视", "3m"])
        if has_p_front:
            lack_list.append([tifs_id, "全色", "前视", "3m"])
        if has_p_down:
            lack_list.append([tifs_id, "全色", "前视", "2m"])  # 原始笔误保留
        if np.sum(sensor_types == "多光谱") == 0:
            lack_list.append([tifs_id, "多光谱", "下视", "8m"])

    elif tif_type == "ZY1":
        if np.sum(sensor_types == "全色") == 0:
            lack_list.append([tifs_id, "全色", "-", "2.5m"])
        if np.sum(sensor_types == "多光谱") == 0:
            lack_list.append([tifs_id, "多光谱", "-", "10m"])

    elif tif_type in ("SV1-03", "SV-2"):
        if np.sum(sensor_types == "全色") == 0:
            lack_list.append([tifs_id, "全色", "-", "0.5m"])
        if np.sum(sensor_types == "多光谱") == 0:
            lack_list.append([tifs_id, "多光谱", "-", "2m"])

    elif tif_type in ("TH01-01","TH01-02","TH01-03","TH01-04"):
        has_p_front = np.sum((sensor_types == "全色") & (sensor_angles == "前视")) == 0
        has_p_down = np.sum((sensor_types == "全色") & (sensor_angles == "下视")) == 0
        has_p_back = np.sum((sensor_types == "全色") & (sensor_angles == "后视")) == 0
        if has_p_front:
            lack_list.append([tifs_id, "全色", "前视", "5m"])
        if has_p_down:
            lack_list.append([tifs_id, "全色", "下视", "5m"])
        if has_p_back:
            lack_list.append([tifs_id, "全色", "后视", "5m"])
        if np.sum(sensor_types == "多光谱") == 0:
            lack_list.append([tifs_id, "多光谱", "下视", "8m"])
        if np.sum(sensor_types == "高分辨") == 0:
            lack_list.append([tifs_id, "高分辨", "下视", "2m"])

    # 转为numpy数组（匹配原始返回格式）
    return np.array(lack_list).reshape(-1, 4) if lack_list else np.array([])


def get_tifs(tifs: list[list[str]], tifs_path: list[list[str]], tif_types: list[str], source_path: str) -> tuple[np.ndarray, np.ndarray]:
    """
    批量处理多组影像：整合所有组的信息和缺失记录（保留原始逻辑）
    参数：
        tifs: 多组影像的名称列表（preprocess_tif返回值）
        tifs_path: 多组影像的路径列表（preprocess_tif返回值）
        tif_types: 多组影像的卫星类型列表（preprocess_tif返回值）
        source_path: 源文件夹路径
    返回：
        所有影像的完整信息数组、所有缺失记录数组
    """
    all_messages = []
    all_lacks = []

    # 遍历每组影像（新增try-except隔离单组异常）
    for idx, (group_names, group_paths, sate_type) in enumerate(zip(tifs, tifs_path, tif_types), 1):
        try:
            # 处理单组影像（原有逻辑保留）
            group_msg = get_tif(group_names, group_paths, sate_type, source_path)
            group_lack = get_lack(group_msg, sate_type)

            # 收集结果（过滤空数组，避免vstack报错）
            if group_msg.size > 0:
                all_messages.append(group_msg)
            if group_lack.size > 0:
                all_lacks.append(group_lack)
            print(f"[处理成功] 第{idx}组影像（卫星类型：{sate_type}）处理完成")
        except Exception as e:
            # 新增：捕获单组处理异常，跳过该组但继续后续处理
            group_name_sample = group_names[0] if group_names else "未知组"
            print(f"[错误] 第{idx}组影像（{group_name_sample}）处理失败，跳过该组：{str(e)}")

    # 合并所有组结果（匹配原始返回格式）
    merged_msg = np.vstack(all_messages) if all_messages else np.array([])
    merged_lack = np.vstack(all_lacks) if all_lacks else np.array([])
    return merged_msg, merged_lack


def to_csv(tifs_message: np.ndarray, tifs_lack: np.ndarray, save_path: str) -> None:
    """
    将影像信息和缺失记录保存为CSV（保留原始格式，支持中文编码）
    参数：
        tifs_message: 所有影像的完整信息数组
        tifs_lack: 所有缺失记录数组
        save_path: 保存文件夹路径
    """
    save_dir = Path(save_path)
    # 确保保存路径存在（原有逻辑保留）
    try:
        save_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        # 新增：捕获创建文件夹权限不足的异常
        raise PermissionError(f"[错误] 无法创建保存文件夹 {save_dir}：{str(e)}\n请检查文件夹权限") from e
    except Exception as e:
        # 新增：捕获创建文件夹的其他异常（如路径非法）
        raise RuntimeError(f"[错误] 创建保存文件夹 {save_dir} 失败：{str(e)}") from e

    # 1. 保存影像信息CSV
    if tifs_message.size > 0:
        msg_columns = [
            "影像型号", "卫星类型", "影像时相", "传感器类型", "传感器角度",
            "分辨率", "是否能打开", "是否损坏", "光谱是否缺失", "是否存在rpc","是否存在rpb", "云占比"
        ]
        msg_df = pd.DataFrame(tifs_message, columns=msg_columns)
        msg_csv_path = save_dir / "message.csv"
        try:
            msg_df.to_csv(msg_csv_path, index=False, encoding="utf-8-sig")
            print(f"[保存成功] 影像信息已保存至：{msg_csv_path}")
        except PermissionError as e:
            # 新增：捕获保存文件权限不足
            print(f"[错误] 保存影像信息失败（{msg_csv_path}）：无写入权限，请检查文件是否被占用或文件夹权限")
        except IOError as e:
            # 新增：捕获磁盘满、文件损坏等IO错误
            print(f"[错误] 保存影像信息失败（{msg_csv_path}）：{str(e)}（可能磁盘空间不足或文件损坏）")
        except Exception as e:
            # 新增：捕获其他意外异常
            print(f"[错误] 保存影像信息失败（{msg_csv_path}）：{str(e)}")
    else:
        print("[警告] 无影像信息可保存，不生成 message.csv")

    # 2. 保存缺失记录CSV（仅当有缺失时）
    if tifs_lack.size > 0:
        lack_columns = ["影像型号", "缺失传感器类型", "缺失传感器角度", "缺失影像分辨率"]
        lack_df = pd.DataFrame(tifs_lack, columns=lack_columns)
        lack_csv_path = save_dir / "lack.csv"
        try:
            lack_df.to_csv(lack_csv_path, index=False, encoding="utf-8-sig")
            print(f"[保存成功] 缺失记录已保存至：{lack_csv_path}")
        except PermissionError as e:
            print(f"[错误] 保存缺失记录失败（{lack_csv_path}）：无写入权限，请检查文件是否被占用或文件夹权限")
        except IOError as e:
            print(f"[错误] 保存缺失记录失败（{lack_csv_path}）：{str(e)}（可能磁盘空间不足或文件损坏）")
        except Exception as e:
            print(f"[错误] 保存缺失记录失败（{lack_csv_path}）：{str(e)}")
    else:
        print("[提示] 无缺失影像，不生成 lack.csv")


def main(img_names: list[str], img_path: str) -> tuple[np.ndarray, np.ndarray]:
    """
    单影像/多影像处理入口（保留原始函数签名和逻辑）
    参数：
        img_names: 单张/多张TIF文件路径列表
        img_path: 源文件夹路径（用于搜索RPC文件）
    返回：
        该批影像的完整信息数组、缺失记录数组
    """
    # 预处理（分组）→ 提取信息 → 返回结果
    tif_types, tifs, tifs_path = preprocess_tif(img_names)
    tifs_message, tifs_lack = get_tifs(tifs, tifs_path, tif_types, img_path)
    return tifs_message, tifs_lack


def validate_tif_files(tif_paths: list[str]) -> list[str]:
    """校验TIF文件是否为有效影像，过滤无效文件"""
    valid_tifs = []
    invalid_tifs = []

    for tif_path in tif_paths:
        tif_file = Path(tif_path)
        try:
            # 1. 尝试用gdal打开文件（非影像文件会返回None）
            data = gdal.Open(tif_path)
            if data is None:
                invalid_tifs.append(f"{tif_file.name}（非影像文件，gdal无法识别）")
                continue

            # 2. 校验影像是否有至少1个波段（排除空影像）
            band_count = data.RasterCount
            if band_count < 1:
                invalid_tifs.append(f"{tif_file.name}（空影像，波段数为0）")
                continue

            # 3. 校验影像宽高是否合法（排除异常小的无效影像）
            if data.RasterXSize < 10 or data.RasterYSize < 10:
                invalid_tifs.append(f"{tif_file.name}（影像尺寸过小，宽/高<10像素，可能为损坏文件）")
                continue

            # 4. 所有校验通过，加入有效列表
            valid_tifs.append(tif_path)

        except Exception as e:
            # 捕获其他异常（如文件损坏、IO错误）
            invalid_tifs.append(f"{tif_file.name}（校验失败：{str(e)[:50]}...）")  # 截取前50字符避免日志过长

    # 输出校验结果
    print(f"\n【文件校验结果】有效TIF文件：{len(valid_tifs)} 个，无效文件：{len(invalid_tifs)} 个")
    if invalid_tifs:
        print("【无效文件列表】")
        for idx, invalid in enumerate(invalid_tifs, 1):
            print(f"  {idx}. {invalid}")

    # 若所有文件均无效，终止程序（避免后续空处理）
    if not valid_tifs:
        raise ValueError("【无有效影像】所有搜索到的.tif/.tiff文件均为无效影像，请检查文件完整性")

    return valid_tifs


# 影像检查运行主函数
def Controller_check_main(img_path):
    # 原始逻辑：逐个处理每张影像，再合并结果（严格保留）
    try:
          # 替换为你的影像文件夹路径
        # 1. 搜索所有TIF文件
        img_names = search_tif(img_path)

        # 2. 校验文件是否为有效影像
        valid_tif_paths = validate_tif_files(img_names)

        # 3. 初始化结果容器
        all_tifs_message = []
        all_tifs_lack = []

        # 4. 逐个处理每张影像（原始循环逻辑）
        for idx, img_file in enumerate(valid_tif_paths, 1):  # 改为处理有效文件，避免重复处理无效文件
            file_path = Path(img_file)
            try:
                file_size = file_path.stat().st_size  # 获取字节数
                # 按1024进制转换为最合适的单位
                if file_size >= 1024 ** 3:  # 1GB及以上
                    file_size_str = f"{file_size / (1024 ** 3):.2f} GB"
                elif file_size >= 1024 ** 2:  # 1MB至1GB之间
                    file_size_str = f"{file_size / (1024 ** 2):.2f} MB"
                else:  # 1MB以下，用KB
                    file_size_str = f"{file_size / 1024:.2f} KB"
            except PermissionError:
                file_size_str = "无法获取（权限不足）"
            except Exception as e:
                file_size_str = f"获取失败：{str(e)[:10]}"

            print(f"\n[处理进度] 正在处理第 {idx}/{len(valid_tif_paths)} 张影像：{Path(img_file).name}（大小：{file_size_str}）")
            # 单张影像处理（传入单文件列表）
            tif_msg, tif_lack = main([img_file], img_path)
            # 收集结果（过滤空数组）
            if tif_msg.size > 0:
                all_tifs_message.append(tif_msg)
            if tif_lack.size > 0:
                all_tifs_lack.append(tif_lack)

        # 5. 合并所有影像结果并保存
        if all_tifs_message:
            merged_all_msg = np.vstack(all_tifs_message)
        else:
            merged_all_msg = np.array([])

        if all_tifs_lack:
            merged_all_lack = np.vstack(all_tifs_lack)
        else:
            merged_all_lack = np.array([])

        # 6. 保存CSV
        to_csv(merged_all_msg, merged_all_lack, img_path)
        print(f"\n[处理完成] 所有影像已处理完毕，结果保存至：{Path(img_path).absolute()}")

    # 新增：全局异常捕获，友好提示错误信息
    except ValueError as e:
        print(f"\n[终止错误-参数/路径问题] {str(e)}")
    except PermissionError as e:
        print(f"\n[终止错误-权限问题] {str(e)}")
    except FileNotFoundError as e:
        print(f"\n[终止错误-文件缺失] {str(e)}")
    except Exception as e:
        print(f"\n[终止错误-未知异常] {str(e)}")
        # 可选：打印异常堆栈，便于调试（生产环境可注释）
        # import traceback
        # traceback.print_exc()

img_path = r"G:\lzy_IQaDS_system\lzy_IQaDS_system_test_data\data_8\TEST"
Controller_check_main(img_path)