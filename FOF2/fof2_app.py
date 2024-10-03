import streamlit as st
import plotly.express as px
import random
import pandas as pd
from pathlib import Path

# Set the title and favicon that appear in the Browser's tab bar.
st.set_page_config(
    page_title='FOF2 angio timings',
    page_icon=':earth_americas:',  # This is an emoji shortcode. Could be a URL too.
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

    # Convert columns to appropriate formats
    df['start'] = pd.to_datetime(df['start_time'])
    df['end'] = pd.to_datetime(df['end_time'])
    df['duration'] = df["end"]-df["start"]
    df['duration[s]'] = df['duration'] / pd.Timedelta('1 second')
    df['id'] = df['idx']
    # df['content'] = df.apply(lambda x: f'Specimen {x.get("specimen")}\nMeasurement {x.get("measurement")}', axis=1)

    return df[['specimen', 'start', 'end', 'duration','duration[s]']]

df = get_timing_data()


def specimen_sorting(spec):
    return sorted(spec,key = lambda x:int(str(x).split("-")[-1]))


specimens = specimen_sorting(df['specimen'].unique())

target_specimens = specimen_sorting(['FOF2-1', 'FOF2-13', 'FOF2-25', 'FOF2-2', 'FOF2-9', 'FOF2-11', 'FOF2-28', 'FOF2-17', 'FOF2-20'])


if len(specimens)==0:
    st.warning("Select at least one specimen")

selected_specimens = st.multiselect(
    'Which specimen(s) would you like to review?',
    specimens,
    target_specimens
)

if len(specimens)>0:
    with st.expander("Measurements of the selected subjects"):
        st.table(df[df['specimen'].isin(selected_specimens)][['specimen','start','end','duration[s]','duration']])
        

    block_dt = st.slider(
        "Maximim distance in MINUTES between measurements",
        min_value=0,max_value=720,value=90, step=5
    )

    def get_random_color():
        """Generate a random hex color."""
        return f"#{random.randint(0, 0xFFFFFF):06x}"



    for s in specimen_sorting(selected_specimens):
        # Filter data for the selected specimen
        filtered_df = df[df.specimen == s].copy().reset_index(drop=True)
        if len(filtered_df.index)==0:
            continue
        
        with st.container(border=True):
            st.header(s, divider=False)
            
            # Initialize block column
            filtered_df['block'] = 1
            
            block = 1
            # Loop through the rows and calculate the time difference (dt)
            for index in range(1, len(filtered_df)):
                prev_end = filtered_df.iloc[index - 1]['end']
                current_start = filtered_df.iloc[index]['start']
                
                # Calculate time difference in hours between the previous row's 'end' and current row's 'start'
                dt = (current_start - prev_end) / pd.Timedelta(minutes=1)  # Calculate the difference in hours
                
                # Check if the time difference is more than X minutes
                if dt > block_dt:
                    block += 1
                
                filtered_df.at[index, 'block'] = block

            filtered_df['color'] = filtered_df['block'].apply(lambda x: get_random_color())

            st.header(s, divider=False)
            
            for b in range(1,block+1):
                _df = filtered_df[filtered_df["block"] ==b ]
                n = len(_df)
                start = _df["start"].min().dt.date
                end = _df["end"].max().dt.date
                if start!=end:
                    st.write(f"Block {b}: {n} measurements from {start} to {end}")
                else:
                    st.write(f"Block {b}: {n} measurements on {start}")
            
            # Plotting each block
            for b in range(1,block+1):
                sub_df = (filtered_df[filtered_df["block"] == b]).copy().sort_values(by="start").reset_index(drop=True)
                
                st.subheader(f"[Block {b}]", divider=True)
                st.write(f"Number of measurements: {len(sub_df.index)} of {len(filtered_df.index)}")
                # Set min and max time ranges for the block
                min_dt = sub_df['start'].min()
                max_dt = sub_df['end'].max()
                
                # Plot the timeline using Plotly Express
                fig = px.timeline(
                    sub_df,
                    x_start='start',
                    x_end='end',
                    y='specimen',
                    color = 'color',
                    hover_data = ['start','end','duration[s]'],
                    height = 150,
                    # range_x=[min_dt, max_dt]
                )

                # Update layout for better presentation
                fig.update_yaxes(categoryorder="total ascending")
                fig.update_layout(showlegend=False)

                # Display the plot in Streamlit
                st.plotly_chart(fig)
                
                with st.expander("Table"):
                    st.table(sub_df[['specimen','start','end','duration[s]','duration']])
            
            st.write("")