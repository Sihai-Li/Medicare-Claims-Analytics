from pathlib import Path

import pandas as pd


# 找到项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 构造原始数据文件路径
INPUT_FILE = PROJECT_ROOT / "data" / "raw" / "inpatient.csv"


def main():
    print(f"Reading: {INPUT_FILE}")

    # 先全部按字符串读取，避免患者编号、诊断代码等丢失前导零
    inpatient = pd.read_csv(
        INPUT_FILE,
        sep="|",
        dtype="string",
        low_memory=False,
    )

    print("\n=== Dataset shape ===")
    print(f"Rows:    {inpatient.shape[0]:,}")
    print(f"Columns: {inpatient.shape[1]:,}")

    print("\n=== Column names ===")
    for number, column in enumerate(inpatient.columns, start=1):
        print(f"{number:>2}. {column}")

    print("\n=== First 3 records ===")
    print(inpatient.head(3).to_string(index=False))


if __name__ == "__main__":
    main()