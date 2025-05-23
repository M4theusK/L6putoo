import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import interp1d

def plot_polar_radiation_pattern(csv_file):
    """
    Plots smooth polar radiation patterns for all frequency columns in the CSV file.
    Interpolates to make curves smooth and extends 0–180° data to 0–360°.
    """
    # Load CSV data
    df = pd.read_csv(csv_file)

    # Original angle and gain
    angles_deg = df["Angle (degrees)"]
    angles_rad = np.radians(angles_deg)

    # Define fine angle resolution (1° steps)
    fine_deg = np.linspace(0, 180, 181)
    fine_rad = np.radians(fine_deg)

    # Prepare polar plot
    plt.figure(figsize=(10, 8), dpi=100)
    ax = plt.subplot(111, polar=True)

    for col in df.columns[1:]:  # Skip angle column
      gain = df[col]

    # Create interpolator
    interpolator = interp1d(angles_deg, gain, kind='cubic')
    fine_gain = interpolator(fine_deg)

    # Mirror data for 0–360°
    extended_angles = np.concatenate([fine_rad, fine_rad + np.pi])
    mirrored_gain = np.concatenate([fine_gain, fine_gain[::-1]])

    # Plot original + 3 rotated versions (90°, 180°, 270°)
    for i in range(4):
        angle_offset = np.radians(i * 90)
        rotated_angles = (extended_angles + angle_offset) % (2 * np.pi)
        (line,) = ax.plot(rotated_angles, mirrored_gain, label=f"{col} +{i*90}°" if i else col)
        ax.fill(rotated_angles, mirrored_gain, color=line.get_color(), alpha=0.3)



    # Customize plot
    ax.set_theta_zero_location("E")  # Set zero to South (bottom)
    ax.set_theta_direction(1)  # Counterclockwise direction to move 90 to the top
    ax.set_ylim(-30, 0)

    # Dotted grid lines and radial ticks
    r_ticks = np.arange(-30, 1, 5)
    ax.set_yticks(r_ticks)
    ax.yaxis.grid(True, linestyle=':', linewidth=1)
    ax.xaxis.grid(True, linestyle=':', linewidth=1)

    # Hide default labels and add transparent ones manually at top
    ax.set_yticklabels([])

    # Adjust tick labels
    for r in r_ticks:
        ax.text(np.deg2rad(90), r, f"{r} dB",
                ha='center', va='center',
                alpha=0.5, fontsize=8)
    plt.show()

# Example usage:
def main():
    plot_polar_radiation_pattern('12.csv')

if __name__ == "__main__":
    main()
