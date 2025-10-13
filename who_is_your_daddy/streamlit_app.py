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
from fractions import Fraction

# --- Load data ---
ROOT_PATH = "who_is_your_daddy"
@st.cache_data
def load_data(path="assets/magassagos.csv", age_limit = 17, min_height = 120):
    df = pd.read_csv(os.path.join(ROOT_PATH,path))
    df = df[df["age"]>=age_limit]
    df = df[df["height"] >= min_height]
    return df

# def compute_cdf(df, displacement_male, displacement_female):
#     from scipy.stats import gaussian_kde
#     df = df.copy()
#     df.loc[df['sex'] == 'male', 'height'] += displacement_male
#     df.loc[df['sex'] == 'female', 'height'] += displacement_female
#     x = np.arange(140, 211, 1)
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



def compute_cdf(df, displacement_male, displacement_female):
    from sklearn.neighbors import KernelDensity
    
    df = df.copy()
    df.loc[df['sex'] == 'male', 'height'] += displacement_male
    df.loc[df['sex'] == 'female', 'height'] += displacement_female

    x = np.arange(140, 211, 1).reshape(-1,1)
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

def height_comparison(df, height_value, threshold, selected_sex):
    df = df[df['sex'] == selected_sex]
    counts = {'lower':0, 'similar':0, 'higher':0}
    for h in df['height']:
        if h < height_value - threshold:
            counts['lower'] += 1
        elif h > height_value + threshold:
            counts['higher'] += 1
        else:
            counts['similar'] += 1
    total = len(df)
    percentages = {k: v / total if total > 0 else 0 for k, v in counts.items()}
    return counts, percentages

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

df = load_data()

st.sidebar.header("Displacement Correction Settings")
disp_male = st.sidebar.slider("Male Height Displacement (cm)", -10.0, 10.0, 3.0, 0.1)
disp_female = st.sidebar.slider("Female Height Displacement (cm)", -10.0, 10.0, 3.0, 0.1)

st.sidebar.header("Comparison Settings")
selected_sex = st.sidebar.selectbox("Select your sex for comparison", options=["male", "female"])
your_height = st.sidebar.slider("Your Height (cm)", 140.0, 210.0, 170.0, step = 0.5)
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
bins = np.arange(140, 211, 2)  # 2 cm széles bin-ek

for sex in ['male', 'female']:
    data = df[df['sex'] == sex]['height'].copy()
    # Apply displacement
    if sex == 'male':
        data += disp_male
    else:
        data += disp_female
    ax_hist.hist(data, bins=bins, alpha=0.5, label=sex.capitalize(), color=colors[sex], edgecolor='black')

ax_hist.set_xlabel("Height (cm)")
ax_hist.set_ylabel("Count")
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
counts, percentages = height_comparison(df, your_height, threshold, selected_sex)

frac_lower = pretty_fraction(percentages['lower'])
frac_similar = pretty_fraction(percentages['similar'])
frac_higher = pretty_fraction(percentages['higher'])

st.subheader(f"Height Comparison for your height: {your_height} cm ({selected_sex.capitalize()})")

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
