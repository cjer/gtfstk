import pytest

import pandas as pd
from pandas.util.testing import assert_series_equal
import numpy as np
import shapely.geometry as sg

from .context import gtfstk, slow, HAS_GEOPANDAS, DATA_DIR, sample, cairns, cairns_dates, cairns_trip_stats
from gtfstk import *


def test_summarize():
    feed = sample.copy()

    with pytest.raises(ValueError):
        summarize(feed, 'bad_table')

    for table in [None, 'stops']:
        f = summarize(feed, table)
        assert isinstance(f, pd.DataFrame)
        expect_cols = {'table', 'column', 'num_values', 'num_nonnull_values',
          'num_unique_values', 'min_value', 'max_value'}
        assert set(f.columns) == expect_cols
        assert f.shape[0]

def test_describe():
    feed = sample.copy() # No distances here
    a = describe(feed)
    assert isinstance(a, pd.DataFrame)
    assert set(a.columns) == set(['indicator', 'value'])

def test_assess_quality():
    feed = sample.copy() # No distances here
    a = assess_quality(feed)
    assert isinstance(a, pd.DataFrame)
    assert set(a.columns) == set(['indicator', 'value'])

def test_convert_dist():
    # Test with no distances
    feed1 = cairns.copy() # No distances here
    feed2 = convert_dist(feed1, 'mi')
    assert feed2.dist_units == 'mi'

    # Test with distances and identity conversion
    feed1 = append_dist_to_shapes(feed1)
    feed2 = convert_dist(feed1, feed1.dist_units)
    assert feed1 == feed2

    # Test with proper conversion
    feed2 = convert_dist(feed1, 'm')
    assert_series_equal(feed2.shapes['shape_dist_traveled']/1000,
      feed1.shapes['shape_dist_traveled'])

def test_compute_feed_stats():
    feed = cairns.copy()
    dates = cairns_dates + ['20010101']
    trip_stats = cairns_trip_stats
    f = compute_feed_stats(feed, trip_stats, dates)
    # Should be a data frame
    assert isinstance(f, pd.core.frame.DataFrame)
    # Should have the correct dates
    assert f.date.tolist() == cairns_dates
    # Should contain the correct columns
    expect_cols = {
      'num_trips',
      'num_trip_starts',
      'num_trip_ends',
      'num_routes',
      'num_stops',
      'peak_num_trips',
      'peak_start_time',
      'peak_end_time',
      'service_duration',
      'service_distance',
      'service_speed',
      'date',
      }
    assert set(f.columns) == expect_cols

    # Empty dates should yield empty DataFrame
    f = compute_feed_stats(feed, trip_stats, [])
    assert f.empty

    # No services should yield null stats
    feed1 = feed.copy()
    c = feed1.calendar
    c['monday'] = 0
    feed1.calendar = c
    f = compute_feed_stats(feed1, trip_stats, dates[0])
    assert set(f.columns) == expect_cols
    assert f.date.iat[0] == dates[0]
    assert pd.isnull(f.num_trips.iat[0])

def test_compute_feed_time_series():
    feed = cairns.copy()
    dates = cairns_dates + ['20010101']
    trip_stats = cairns_trip_stats
    f = compute_feed_time_series(feed, trip_stats, dates, freq='1H')
    # Should be a data frame
    assert isinstance(f, pd.core.frame.DataFrame)
    # Should have the correct number of rows
    assert f.shape[0] == 24*2
    # Should have the correct columns
    expect_cols = {
      'num_trip_starts',
      'num_trip_ends',
      'num_trips',
      'service_distance',
      'service_duration',
      'service_speed',
      }
    assert set(f.columns) == expect_cols

    # Empty check
    f = compute_feed_time_series(feed, trip_stats, [])
    assert f.empty

    # No services should yield null stats
    feed1 = feed.copy()
    c = feed1.calendar
    c['monday'] = 0
    feed1.calendar = c
    f = compute_feed_time_series(feed1, trip_stats, dates[0])
    assert set(f.columns) == expect_cols
    assert pd.isnull(f.values).all()

def test_create_shapes():
    feed1 = cairns.copy()
    # Remove a trip shape
    trip_id = 'CNS2014-CNS_MUL-Weekday-00-4165878'
    feed1.trips.loc[feed1.trips['trip_id'] == trip_id, 'shape_id'] = np.nan
    feed2 = create_shapes(feed1)
    # Should create only 1 new shape
    assert len(set(feed2.shapes['shape_id']) - set(
      feed1.shapes['shape_id'])) == 1

    feed2 = create_shapes(feed1, all_trips=True)
    # Number of shapes should equal number of unique stop sequences
    st = feed1.stop_times.sort_values(['trip_id', 'stop_sequence'])
    stop_seqs = set([tuple(group['stop_id'].values)
      for __, group in st.groupby('trip_id')])
    assert feed2.shapes['shape_id'].nunique() == len(stop_seqs)

def test_compute_bounds():
    feed = cairns.copy()
    minlon, minlat, maxlon, maxlat = compute_bounds(feed)
    # Bounds should be in the ball park
    assert 145 < minlon < 146
    assert 145 < maxlon < 146
    assert -18 < minlat < -15
    assert -18 < maxlat < -15

def test_compute_convex_hull():
    feed = cairns.copy()
    hull = compute_convex_hull(feed)
    assert isinstance(hull, sg.Polygon)
    # Hull should encompass all stops
    m = sg.MultiPoint(feed.stops[['stop_lon', 'stop_lat']].values)
    assert hull.contains(m)

def test_compute_center():
    feed = cairns.copy()
    centers = [compute_center(feed), compute_center(feed, 20)]
    bounds = compute_bounds(feed)
    for lon, lat in centers:
        # Center should be in the ball park
        assert bounds[0] < lon < bounds[2]
        assert bounds[1] < lat < bounds[3]

def test_restrict_by_routes():
    feed1 = cairns.copy()
    route_ids = feed1.routes['route_id'][:2].tolist()
    feed2 = restrict_to_routes(feed1, route_ids)
    # Should have correct routes
    assert set(feed2.routes['route_id']) == set(route_ids)
    # Should have correct trips
    trip_ids = feed1.trips[feed1.trips['route_id'].isin(
      route_ids)]['trip_id']
    assert set(feed2.trips['trip_id']) == set(trip_ids)
    # Should have correct shapes
    shape_ids = feed1.trips[feed1.trips['trip_id'].isin(
      trip_ids)]['shape_id']
    assert set(feed2.shapes['shape_id']) == set(shape_ids)
    # Should have correct stops
    stop_ids = feed1.stop_times[feed1.stop_times['trip_id'].isin(
      trip_ids)]['stop_id']
    assert set(feed2.stop_times['stop_id']) == set(stop_ids)

@pytest.mark.skipif(not HAS_GEOPANDAS, reason="Requires GeoPandas")
def test_restrict_to_polygon():
    feed1 = cairns.copy()
    with (DATA_DIR/'cairns_square_stop_750070.geojson').open() as src:
        polygon = sg.shape(json.load(src)['features'][0]['geometry'])
    feed2 = restrict_to_polygon(feed1, polygon)
    # Should have correct routes
    rsns = ['120', '120N']
    assert set(feed2.routes['route_short_name']) == set(rsns)
    # Should have correct trips
    route_ids = feed1.routes[feed1.routes['route_short_name'].isin(
      rsns)]['route_id']
    trip_ids = feed1.trips[feed1.trips['route_id'].isin(
      route_ids)]['trip_id']
    assert set(feed2.trips['trip_id']) == set(trip_ids)
    # Should have correct shapes
    shape_ids = feed1.trips[feed1.trips['trip_id'].isin(
      trip_ids)]['shape_id']
    assert set(feed2.shapes['shape_id']) == set(shape_ids)
    # Should have correct stops
    stop_ids = feed1.stop_times[feed1.stop_times['trip_id'].isin(
      trip_ids)]['stop_id']
    assert set(feed2.stop_times['stop_id']) == set(stop_ids)

@slow
@pytest.mark.skipif(not HAS_GEOPANDAS, reason="Requires GeoPandas")
def test_compute_screen_line_counts():
    feed = cairns.copy()
    dates = cairns_dates + ['20010101']
    trip_stats = cairns_trip_stats
    feed = append_dist_to_stop_times(feed, trip_stats)

    # Load screen line
    with (DATA_DIR/'cairns_screen_line.geojson').open() as src:
        line = json.load(src)
        line = sg.shape(line['features'][0]['geometry'])

    f = compute_screen_line_counts(feed, line, dates)

    # Should have correct columns
    expect_cols = {'date', 'trip_id', 'route_id', 'route_short_name',
      'crossing_time', 'orientation'}
    assert set(f.columns) == expect_cols

    # Should have correct routes
    rsns = ['120', '120N']
    assert set(f['route_short_name']) == set(rsns)

    # Should have correct number of trips
    num_unique_trips = 34
    assert f['trip_id'].nunique() == num_unique_trips

    # Should have correct orientations
    for ori in [-1, 1]:
        assert f[f['orientation'] == ori].shape[0] == 2*num_unique_trips

    # Should only have feed dates
    assert f.date.unique().tolist() == cairns_dates

    # Empty check
    f = compute_screen_line_counts(feed, line, [])
    assert f.empty
