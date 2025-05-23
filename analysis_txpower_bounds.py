from pathlib import Path
import pandas
import matplotlib.pyplot as plt

def read_file(file):
    df = pandas.read_csv(file, sep='\t', skiprows=1)
    return df

data_all = {file.stem: read_file(file) for file in Path('.').glob('txpower_bounds/*.tsv')}

for file, data in data_all.items():
    print(f"{file} cycle_count={data['cycle'].nunique()}")

for file, data in data_all.items():
    signal_by_txpower = data.groupby('txpower')['signal_strength']

    x = signal_by_txpower.mean().index
    y = signal_by_txpower.mean()

    print(file)
    plt.violinplot(signal_by_txpower.apply(list), list(x), widths=60, showmeans=True, showextrema=False)
    plt.show()
