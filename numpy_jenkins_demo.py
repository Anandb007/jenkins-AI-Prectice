import numpy as np

print("=== NumPy demo ===")

# 1D array (durations in seconds)
durations = np.array([120, 45, 30, 90, 60])
print("Durations (1D):", durations)
print("Shape:", durations.shape)
print("Mean:", np.mean(durations))
print("Vectorized * 2:", durations * 2)

# From Pandas CSV if present
try:
    import pandas as pd
    df = pd.read_csv("builds.csv")
    if "duration_sec" in df.columns:
        arr = df["duration_sec"].values
        print("\nFrom builds.csv (duration_sec as NumPy array):", arr)
        print("Shape:", arr.shape)
        print("Mean:", np.mean(arr))
except FileNotFoundError:
    print("\n(builds.csv not found — run pandas_jenkins_demo.py first to generate it)")

# 2D array: rows = builds, cols = [duration_sec, pass=1/fail=0]
data = np.array([
    [120, 1],
    [45, 0],
    [30, 1],
])
print("\n2D array (duration, pass/fail):")
print(data)
print("Shape:", data.shape)
print("First column (durations):", data[:, 0])
print("Mean duration:", np.mean(data[:, 0]))
