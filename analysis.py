from pathlib import Path
import pandas
import matplotlib.pyplot as plt
import scipy.optimize
import numpy as np

def read_file(file):
    df = pandas.read_csv(file, sep='\t', skiprows=1)
    df = df[df['txpower'] >= 200]
    return df

data_all = {file.stem: read_file(file) for file in sorted(Path('.').glob('adapter_comparison/*_xxxx-xx-xx.tsv'))}

for file, data in data_all.items():
    print(f"{file} cycle_count={data['cycle'].nunique()}")
    if data['run_hash'].nunique() != 1:
        raise AssertionError(f"Multiple runs in {file}, need manual filtering")

data = data_all['Name_xxxx_xx_xx']

count_by_cycle = data.groupby('cycle').size()
x = count_by_cycle.index
y = count_by_cycle
plt.plot(x, y)
plt.ylim(0)

signal_by_txpower = data.groupby('txpower')['signal_strength']

x = signal_by_txpower.mean().index
y = signal_by_txpower.mean()

params, _ = scipy.optimize.curve_fit(lambda x, b: x / 100 + b, x, y, p0=-80)

print(*params)

#plt.plot(x, x / 100 + params[0])
plt.violinplot(signal_by_txpower.apply(list), list(x), widths=60, showmeans=True, showextrema=False);

def logistic(x, L, k, x0):
    return L / (1 + np.exp(-k * (x - x0)))

def logistic_inverse(y, L, k, x0):
    return - np.log(L / y - 1) / k + x0

colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
plt.figure(figsize=(10, 7.5))

for i, (name, data) in enumerate(data_all.items()):
    cycle_count = data['cycle'].nunique()
    count_by_txpower = data.groupby('txpower').size()
    x = count_by_txpower.index
    y = count_by_txpower / (cycle_count * 10) * 100

    params, _ = scipy.optimize.curve_fit(logistic, x, y, p0=(100, 0.01, 1000), bounds=([50, 0, 0], [100, 1, 3000]))

    print(name)
    print(*params)
    print(logistic_inverse(50, *params))

    # plt.plot(x, logistic(x, *params), '--', color=colors[i], alpha=0.2)
    plt.plot(x, y, '-', label=name, color=colors[i])

plt.xlabel('Transmit power (mBm)')
plt.ylabel('Received packets (%)')
plt.legend();
