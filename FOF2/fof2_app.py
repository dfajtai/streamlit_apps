import streamlit as st
import plotly.express as px

import pandas as pd

from pathlib import Path

# Set the title and favicon that appear in the Browser's tab bar.
st.set_page_config(
    page_title='FOF2 angio timings',
    page_icon=':earth_americas:', # This is an emoji shortcode. Could be a URL too.
)

# -----------------------------------------------------------------------------
# Declare some useful functions.

@st.cache_data
def get_timing_data():
    """Grab timing data from a CSV file.

    This uses caching to avoid having to read the file every time. If we were
    reading from an HTTP endpoint instead of a file, it's a good idea to set
    a maximum age to the cache with the TTL argument: @st.cache_data(ttl='1d')
    """

    # Instead of a CSV on disk, you could read from an HTTP endpoint here too.
    DATA_FILENAME = Path(__file__).parent/'data/measurements.csv'
    df = pd.read_csv(DATA_FILENAME)

    
    # Convert years from string to integers
    df['start'] = pd.to_datetime(df['start_time'])
    df['end'] = pd.to_datetime(df['end_time'])
    df['group'] = df['specimen']
    df['id'] = df['idx']
    df['content'] = df.apply(lambda x:f'Specimen {x.get("specimen")}\nMeasurement {x.get("measurement")}', axis=1 )
    

    return df[['id','content','start','end','group']]

df = get_timing_data()

# Add some spacing
''
''
groups = df['group'].unique()

if not len(groups):
    st.warning("Select at least one specimen")
    

selected_specimens = st.multiselect(
    'Which specimen(s) would you like to review?',
    groups,
    ['FOF2-1','FOF2-13','FOF2-25','FOF2-2','FOF2-9','FOF2-11','FOF2-28','FOF2-17','FOF2-20'])
    
    
filtered_df = df[df['group'].isin(selected_specimens)]

items = filtered_df.to_dict()

groups = [{'id':g,'content':g,'style':'color: black; background-color: #a9a9a98F;'} for g in groups]
    
    

# Plot the timeline using Plotly Express
fig = px.timeline(
    filtered_df,
    x_start='start',
    x_end='end',
    y='specimen',
    color='specimen',
    title="Measurement Timeline"
)

# Update layout for better presentation
fig.update_yaxes(categoryorder="total ascending")
fig.update_layout(showlegend=False)

# Display the plot in Streamlit
st.plotly_chart(fig)