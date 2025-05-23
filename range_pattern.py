import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import interp1d

def plot_polar_radiation_pattern(csv_file):
    """
    Plots polar detection range patterns for all frequency columns in the CSV file.
    Converts antenna gain in dB to detection range using free-space path loss approximation.
    Assumes maximum range is 7.8 km at 0 dB.
    """
    # Load CSV data
    df = pd.read_csv(csv_file)

    # Original angle and gain
    angles_deg = df["Angle (degrees)"]
    angles_rad = np.radians(angles_deg)

    # Fine interpolation angles (1° steps)
    fine_deg = np.linspace(0, 180, 181)
    fine_rad = np.radians(fine_deg)

    # Prepare polar plot
    plt.figure(figsize=(10, 8), dpi=100)
    ax = plt.subplot(111, polar=True)

    for col in df.columns[1:]:  # Skip the angle column
        gain = df[col]

        # Interpolate gain values
        interpolator = interp1d(angles_deg, gain, kind='cubic')
        fine_gain = interpolator(fine_deg)

        # Mirror data to 0–360°
        extended_angles = np.concatenate([fine_rad, fine_rad + np.pi])
        mirrored_gain = np.concatenate([fine_gain, fine_gain[::-1]])

        # Convert gain (dB) to detection range (km)
        max_range_km = 10.2  # Maximum detection range at 0 dB
        mirrored_range = max_range_km * 10**(mirrored_gain / 20)

        # Plot original + 3 rotated versions (90°, 180°, 270°)
        for i in range(4):
            angle_offset = np.radians(i * 90)
            rotated_angles = (extended_angles + angle_offset) % (2 * np.pi)
            (line,) = ax.plot(rotated_angles, mirrored_range, label=f"{col} +{i*90}°" if i else col)
            ax.fill(rotated_angles, mirrored_range, color=line.get_color(), alpha=0.3)

    # Customize polar plot
    ax.set_theta_zero_location("E")  # Set 0° at East (right)
    ax.set_theta_direction(1)  # Counterclockwise

    # Set radial limit based on max range
    ax.set_ylim(0, max_range_km)
    r_ticks = np.linspace(0, max_range_km, 6)
    ax.set_yticks(r_ticks)
    ax.set_yticklabels([])  # Hide default radial labels

    # Add custom radial labels at top
    for r in r_ticks:
        ax.text(np.deg2rad(90), r, f"{r:.1f} km",
                ha='center', va='center',
                alpha=0.5, fontsize=8)

    # Grid style
    ax.yaxis.grid(True, linestyle=':', linewidth=1)
    ax.xaxis.grid(True, linestyle=':', linewidth=1)

    plt.show()

# Example usage
def main():
    plot_polar_radiation_pattern('12.csv')

if __name__ == "__main__":
    main()
