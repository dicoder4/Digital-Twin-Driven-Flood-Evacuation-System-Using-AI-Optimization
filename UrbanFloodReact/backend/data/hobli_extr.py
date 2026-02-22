import pandas as pd
df = pd.read_parquet("21_Bengaluru _Rural hobli details.parquet")
df.to_csv("rural_hobli.csv", index=False)
