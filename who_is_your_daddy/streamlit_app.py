"""
Height Data Analysis and Comparison App

Data source: Static CSV file 'magassagos.csv' derived from hospital records.

Reference datasets for average height and percentiles used for displacement adjustment and comparison:
- Hungarian height statistics: https://antropologia.elte.hu/_testmagassg1.html
- Average adult human height by country and region: https://en.wikipedia.org/wiki/Average_human_height_by_country
"""

import os
import streamlit as st
import pandas as pd
import numpy as np

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from fractions import Fraction

# --- Load data ---
ROOT_PATH = "who_is_your_daddy"
ROOT_PATH = ""

sample_path = "assets/small_sample.csv"

cdf_min = 135.0
cdf_max = 220.0

@st.cache_data
def load_data(data_path, age_limit = 17, min_height = 120):
    df_path = os.path.join(ROOT_PATH,data_path)
    df = pd.read_csv(df_path)
    df = df[df["age"]>=age_limit]
    df = df[df["height"] >= min_height]
    return df

# --- Load data with bootstrap for big sample ---
def load_data_new(data_path, use_bootstrap=False, bootstrap_n=None, seed=42, age_limit=17, min_height=120, max_height = 250):
    df_path = os.path.join(ROOT_PATH,data_path)
    df = pd.read_csv(df_path)

    df = df[df["age"] >= age_limit]
    if df["height"].apply(lambda x: x<min_height).all():
        df["height"] =df["height"].apply(lambda x: x * 100.0)

    df = df[(df["height"] >= min_height) & (df["height"] <= max_height)]
    if use_bootstrap and isinstance(bootstrap_n, int) and bootstrap_n > 0:
        # The size must not exceed the actual DataFrame unless sampling with replacement
        # Here, .sample(..., replace=True) can handle bootstrap_n > len(df)
        df = df.sample(n=bootstrap_n, replace=True, random_state=seed, ignore_index=True).reset_index(drop=True)
        # print(df.describe())
    return df

# def compute_cdf(df, displacement_male, displacement_female):
#     from scipy.stats import gaussian_kde
#     df = df.copy()
#     df.loc[df['sex'] == 'male', 'height'] += displacement_male
#     df.loc[df['sex'] == 'female', 'height'] += displacement_female
#     x = np.arange(cdf_min, 211, 1)
#     cdf_results = {}
#     for sex in ['male', 'female']:
#         data = df[df['sex'] == sex]['height'].dropna().values
#         if len(data) > 1:
#             kde = gaussian_kde(data)
#             pdf = kde(x)
#             cdf = np.cumsum(pdf)
#             cdf /= cdf[-1]
#             cdf_results[sex] = (x, cdf)
#         else:
#             cdf_results[sex] = (x, np.zeros_like(x))
#     return cdf_results



def compute_cdf(df, displacement_male, displacement_female, cdf_step = 0.5):
    from sklearn.neighbors import KernelDensity
    
    df = df.copy()
    df.loc[df['sex'] == 'male', 'height'] += displacement_male
    df.loc[df['sex'] == 'female', 'height'] += displacement_female

    x = np.arange(cdf_min, cdf_max+1, cdf_step).reshape(-1,1)
    cdf_results = {}

    for sex in ['male', 'female']:
        data = df[df['sex'] == sex]['height'].dropna().values.reshape(-1,1)
        if len(data) > 1:
            kde = KernelDensity(kernel='gaussian', bandwidth=1.0).fit(data)
            log_pdf = kde.score_samples(x)
            pdf = np.exp(log_pdf)
            cdf = np.cumsum(pdf)
            cdf /= cdf[-1]
            cdf_results[sex] = (x.flatten(), cdf)
        else:
            cdf_results[sex] = (x.flatten(), np.zeros_like(x.flatten()))
    return cdf_results

def percentile_table(cdf_results, percentiles=[1,3,10,25,50,75,90,95,99]):
    tables = {}
    for sex, (x, cdf) in cdf_results.items():
        table = {}
        for p in percentiles:
            idx = np.searchsorted(cdf, p/100)
            table[p] = x[idx] if idx < len(x) else x[-1]
        tables[sex] = table
    return tables

def height_comparison_from_cdf(df, cdf_results, height_value, threshold, selected_sex):
    """
    Compare given height to CDF data with threshold.
    
    Args:
        df (pd.DataFrame): dataframe
        cdf_results (dict): {'male': (x_vals, cdf_vals), 'female': (x_vals, cdf_vals)}
        height_value (float): magasság cm-ben
        threshold (float): ± érték, amin belül 'hasónló'
        selected_sex (str): 'male' vagy 'female'
        total_count (float): az elemszám, amire az arányokat vissza kell vetíteni (pl. a csoport elemszáma)
        
    Returns:
        counts (dict): {'lower', 'similar', 'higher'} elemszám becslés (összes elemszám total_count)
        percentages (dict): arányok 0..1 között
    """
    x, cdf = cdf_results[selected_sex]
    nrow = df["sex"].apply(lambda x: x=="male").sum()

    low_bound = height_value - threshold
    high_bound = height_value + threshold

    idx_low = np.searchsorted(x, low_bound, side='right') - 1
    idx_high = np.searchsorted(x, high_bound, side='right') - 1

    idx_low = max(0, min(idx_low, len(cdf)-1))
    idx_high = max(0, min(idx_high, len(cdf)-1))

    lower_fraction = cdf[idx_low] if idx_low >= 0 else 0.0
    higher_fraction = 1.0 - cdf[idx_high] if idx_high >= 0 else 0.0
    similar_fraction = 1.0 - lower_fraction - higher_fraction
    if similar_fraction < 0:
        similar_fraction = 0.0

    counts = {
        'lower': int(np.ceil(lower_fraction * nrow)),
        'similar': int(np.ceil(similar_fraction * nrow)),
        'higher': int(np.ceil(higher_fraction * nrow))
    }
    percentages = {
        'lower': lower_fraction,
        'similar': similar_fraction,
        'higher': higher_fraction
    }
    return counts, percentages, nrow

def pretty_fraction(x, max_denominator=100):
    frac = Fraction(x).limit_denominator(max_denominator)
    if frac.denominator == 1:
        return f"{frac.numerator}"
    else:
        return f"{frac.numerator}/{frac.denominator}"

def fraction_to_5_scale(x):
    val = 5 * x
    if val < 0.1:
        return f"{val:.3f}"
    else:
        return f"{val:.1f}"

st.set_page_config(page_title="Who's your daddy")
st.title("Who's your daddy - a Height Analysis and Comparison App")


with st.sidebar.expander("Sample Selection", expanded=False):
    sample_choice = st.radio(
        "Which sample to use?",
        options=["Small sample (~9.4k)", "Big sample (bootstrapped from ~40k)"],
        index=0
    )

    if sample_choice == "Big sample (bootstrapped from ~40k)":
        bootstrap_n = st.slider(
            "Number of samples (bootstrapped rows)",
            min_value=5000,
            max_value=20000,
            value=10000,
            step=1000
        )
        col1, col2 = st.columns(2)
        with col1:
            load_action = st.button("Load sample", use_container_width = True)
        with col2:
            reload_action = st.button("Reload sample",  use_container_width = True)
    else:
        bootstrap_n = None
        load_action = reload_action = False

# --- Select file path and bootstrap settings based on choice ---
if sample_choice == "Small sample (~9.4k)":
    sample_path = "assets/small_sample.csv"
    use_bootstrap = False
else:
    sample_path = "assets/big_sample.csv"
    use_bootstrap = True

if "random_seed" not in st.session_state:
    st.session_state.random_seed = 42  # default seed for first load

# When Load button pressed, seed resets to 42
if load_action:
    st.session_state.random_seed = 42

# When Reload button pressed, seed changes to a new random number
if reload_action:
    st.session_state.random_seed = np.random.randint(0, 10**6)

# Load or reload data using current seed in session_state
if "df" not in st.session_state or load_action or reload_action:
    st.session_state.df = load_data_new(
        sample_path,
        use_bootstrap=use_bootstrap,
        bootstrap_n=bootstrap_n if use_bootstrap else None,
        seed=st.session_state.random_seed,
        min_height=cdf_min,
        max_height=cdf_max
    )

df = st.session_state.df

st.sidebar.header("Displacement Correction Settings")
disp_male = st.sidebar.slider("Male Height Displacement (cm)", -10.0, 10.0, 3.0, 0.1)
disp_female = st.sidebar.slider("Female Height Displacement (cm)", -10.0, 10.0, 3.0, 0.1)

st.sidebar.header("Comparison Settings")
selected_sex = st.sidebar.selectbox("Select your sex for comparison", options=["male", "female"])
your_height = st.sidebar.slider("Your Height (cm)", cdf_min, cdf_max, 170.0, step = 0.5)
threshold = st.sidebar.slider("Threshold (cm)", 0.0, 20.0, 5.0, step = 0.5)

# 1. Basic stats on original data (no displacement)
st.subheader("Basic Descriptive Statistics by Sex (Original Data)")
stats_original = df.groupby('sex')['height'].agg(['count','mean', 'median', 'min', 'max', 'std']).round(2).reset_index()
st.dataframe(stats_original)

# 1a. Show displaced stats if displacement is not zero
if disp_male != 0.0 or disp_female != 0.0:
    stats_displaced = stats_original.copy()
    stats_displaced['mean'] = stats_displaced.apply(
        lambda row: row['mean'] + (disp_male if row['sex']=='male' else disp_female), axis=1)
    stats_displaced['median'] = stats_displaced.apply(
        lambda row: row['median'] + (disp_male if row['sex']=='male' else disp_female), axis=1)
    stats_displaced['min'] = stats_displaced.apply(
        lambda row: row['min'] + (disp_male if row['sex']=='male' else disp_female), axis=1)
    stats_displaced['max'] = stats_displaced.apply(
        lambda row: row['max'] + (disp_male if row['sex']=='male' else disp_female), axis=1)
    stats_displaced['std'] = stats_displaced['std']  # std stays same
    st.subheader("Basic Descriptive Statistics by Sex (After Displacement)")
    st.dataframe(stats_displaced)

st.subheader("Height Distribution Histogram by Sex (With Displacement)")
fig_hist, ax_hist = plt.subplots()
colors = {'male':'blue', 'female':'red'}
bins = np.arange(cdf_min, cdf_max+1, 2)  # 2 cm széles bin-ek

for sex in ['male', 'female']:
    data = df[df['sex'] == sex]['height'].copy()
    # Apply displacement
    if sex == 'male':
        data += disp_male
    else:
        data += disp_female
    ax_hist.hist(data, bins=bins, alpha=0.5, label=sex.capitalize(), color=colors[sex], edgecolor='black')

# Set major ticks every 10 cm
ax_hist.xaxis.set_major_locator(ticker.MultipleLocator(10))

# Set minor ticks every 5 cm
ax_hist.xaxis.set_minor_locator(ticker.MultipleLocator(5))

# Optionally, enable grid for major and minor ticks
# Major grid lines: vertical only, lighter opacity
ax_hist.grid(which='major', axis='x', linestyle='-', linewidth=0.5, color='gray', alpha=0.3)

# Minor grid lines: vertical only, dashed and even lighter
ax_hist.grid(which='minor', axis='x', linestyle='--', linewidth=0.3, color='gray', alpha=0.3)

ax_hist.set_xlabel("Height (cm)")
ax_hist.set_ylabel("Count")

# --- DRAW VERTICAL LINE AND LABEL ---

# Get current y-axis limits
y_min, y_max = ax_hist.get_ylim()

# Increase upper y-limit by 20% for substantial room
y_new_max = y_max * 1.1
ax_hist.set_ylim(y_min, y_new_max)

# Determine color based on selected sex
line_color = 'blue' if selected_sex == 'male' else 'red'

# Draw vertical dashed line at your_height, spanning up to original y_max
ax_hist.vlines(
    x=your_height, ymin=y_min, ymax=y_max,
    colors=line_color, linestyles='dashed', linewidth=2
)

# Place rotated label at the top inside the diagram, well above the tallest bar
label_y_pos = y_max   # halfway into the extra headroom

ax_hist.text(
    your_height,                # small left offset
    label_y_pos,                      # higher up, inside the diagram
    "Your height",
    color=line_color,
    rotation=0,
    verticalalignment='bottom',       # bottom of text at this y
    horizontalalignment='center',
    fontsize=7,                       # smaller font for fit
    fontweight='normal',
    bbox=dict(boxstyle="round", ec="black", fc="white", alpha=0.7)
)


ax_hist.legend()
st.pyplot(fig_hist)

# 2. CDF with displacement
cdf_results = compute_cdf(df, disp_male, disp_female)

st.subheader("Cumulative Distribution (CDF) by Sex (With Displacement)")
fig, ax = plt.subplots()
ax.plot(cdf_results['male'][0], cdf_results['male'][1], label="Male CDF", color='blue')
ax.plot(cdf_results['female'][0], cdf_results['female'][1], label="Female CDF", color='red')
ax.set_xlabel("Height (cm)")
ax.set_ylabel("Cumulative Probability")
ax.legend()
st.pyplot(fig)

# 3. Percentile Table with displacement
percentiles = [1, 3, 10, 25, 50, 75, 90, 95, 99]
percentile_vals = percentile_table(cdf_results, percentiles)

st.subheader("Percentile Table (cm) (With Displacement)")
for sex in ['male', 'female']:
    st.markdown(f"**{sex.capitalize()}**")
    df_p = pd.DataFrame(list(percentile_vals[sex].items()), columns=["Percentile (%)", "Height (cm)"])
    st.table(df_p)

# 4. Height comparison for user inputs
counts, percentages, total = height_comparison_from_cdf(df = df,
                                                        cdf_results= cdf_results, 
                                                        height_value=your_height,
                                                        threshold=threshold, 
                                                        selected_sex=selected_sex, 
                                                        )

frac_lower = pretty_fraction(percentages['lower'])
frac_similar = pretty_fraction(percentages['similar'])
frac_higher = pretty_fraction(percentages['higher'])

st.subheader(f"CDF Based Height Comparison: {your_height} cm ({selected_sex.capitalize()[0]})")

table_data = {
    "Category": ["Shorter", "Similar Height", "Taller"],
    "Count": [counts['lower'], counts['similar'], counts['higher']],
    "Percentage": [percentages['lower']*100.0, percentages['similar']*100.0, percentages['higher']*100.0],
    "Fraction": [frac_lower, frac_similar, frac_higher],
    "5 out of 5": [fraction_to_5_scale(percentages['lower']), fraction_to_5_scale(percentages['similar']), fraction_to_5_scale(percentages['higher'])]
}
st.table(pd.DataFrame(table_data))

fig2, ax2 = plt.subplots()
labels = [
    f"Shorter ({frac_lower})",
    f"Similar Height ({frac_similar})",
    f"Taller ({frac_higher})"
]
colors = ['#66b3ff', '#99ff99', '#ff9999']
ax2.pie(list(percentages.values()), labels=labels, autopct='%1.1f%%', colors=colors)
st.pyplot(fig2)

# References
st.markdown("---")
st.markdown("### References")
st.markdown(
    "- [Hungarian height statistics](https://antropologia.elte.hu/_testmagassg1.html)\n"
    "- [Average human height by country](https://en.wikipedia.org/wiki/Average_human_height_by_country)"
)
