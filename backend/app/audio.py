from __future__ import annotations

import hashlib
import math
from pathlib import Path

import librosa
import numpy as np

from .models import AudioFeatures, AudioProvenance, MetricValue, SegmentFeatures

TARGET_SAMPLE_RATE = 22_050
SEGMENT_COUNT = 6
EXTRACTOR_VERSION = 'extended-2.0'


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _normalize(value: float, low: float, high: float) -> float:
    if high <= low:
        raise ValueError('Normalization range must have positive width')
    return _clamp((value - low) / (high - low))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _scalar(value: object) -> float:
    array = np.asarray(value, dtype=float).reshape(-1)
    return float(array[0]) if array.size else 0.0


def _segment_features(y: np.ndarray, sample_rate: int, duration: float) -> list[SegmentFeatures]:
    segments: list[SegmentFeatures] = []
    boundaries = np.linspace(0, len(y), SEGMENT_COUNT + 1, dtype=int)

    for index in range(SEGMENT_COUNT):
        start_sample = int(boundaries[index])
        end_sample = int(boundaries[index + 1])
        segment = y[start_sample:end_sample]
        start_seconds = start_sample / sample_rate
        end_seconds = min(duration, end_sample / sample_rate)
        segment_duration = max(end_seconds - start_seconds, 1e-6)

        if segment.size < 32:
            rms = 0.0
            centroid = 0.0
            onset_density = 0.0
        else:
            rms = float(np.mean(librosa.feature.rms(y=segment)))
            centroid_values = librosa.feature.spectral_centroid(y=segment, sr=sample_rate)
            centroid = float(np.mean(centroid_values))
            onset_count = len(librosa.onset.onset_detect(y=segment, sr=sample_rate, units='time'))
            onset_density = onset_count / segment_duration

        segments.append(
            SegmentFeatures(
                id=f'segment-{index + 1:02d}',
                start_seconds=round(start_seconds, 4),
                end_seconds=round(end_seconds, 4),
                rms_energy=round(rms, 6),
                onset_density_hz=round(onset_density, 6),
                spectral_centroid_hz=round(centroid, 3),
            )
        )

    return segments


def _metric(
    value: float, low: float, high: float, unit: str, method: str, confidence: float,
    transform: str = 'linear',
) -> MetricValue:
    """One measurement, normalised onto 0..1 for the score to read.

    `transform` exists because a linear range is the wrong instrument for several of
    these quantities, and the 14-track corpus made that visible rather than theoretical.
    Spectral flatness runs 0.0001 / 0.0037 / 0.055 across min / median / max: on a linear
    range almost every recording lands in the bottom fifth, so the normalised value stops
    separating anything. Harmonic ratio has the mirror problem, bunched against 1.0
    because most music is harmonic. Tempo, spectral centroid and spectral contrast are
    perceived logarithmically in the first place -- a doubling matters, not an addition.

    Ranges and transforms are derived from the corpus by
    `backend/scripts/calibrate_audio_ranges.py`; the raw `value` is always reported
    untransformed, so the report still shows the measurement in its own units.
    """
    raw = float(value)
    if transform == 'log':
        mapped = math.log(max(raw, 1e-12))
    elif transform == 'logit':
        clipped = min(1.0 - 1e-6, max(1e-6, raw))
        mapped = math.log(clipped / (1.0 - clipped))
    else:
        mapped = raw
    return MetricValue(
        value=round(raw, 6), normalized=_normalize(mapped, low, high),
        unit=unit, method=method, confidence=confidence)


def _periodicity(y: np.ndarray, sample_rate: int, hop: int = 1024) -> float:
    """How strongly the piece repeats at a fixed period.

    The first version of this measurement asked what fraction of a
    `librosa.segment.recurrence_matrix` was non-zero. That was wrong, and the error is
    worth recording: with `mode='affinity'` the matrix is sparsified to a fixed number of
    nearest neighbours per frame, so the non-zero fraction is roughly constant whatever
    the music does. Measured across a strict two-second loop, a noise field, and a
    through-composed piece, it returned 0.078, 0.064 and 0.073 -- it was reporting the
    algorithm's sparsification parameter, not the music.

    What repetition actually means is that material *returns*, which requires it to have
    left. A drone is maximally self-similar and not at all repetitive, so a raw
    similarity fraction cannot be the answer either.

    So: build a self-similarity matrix over chroma and timbre, take the mean similarity
    along each time lag, and ask whether the strongest lag has **harmonics** -- a piece
    that repeats every two seconds also matches itself at four and six. A comb of peaks
    is periodicity; a single elevated region is only continuity. Lags shorter than 1.5 s
    are excluded because adjacent frames are similar in any recording.
    """
    chroma = librosa.feature.chroma_cqt(y=y, sr=sample_rate, hop_length=hop)
    mfcc = librosa.feature.mfcc(y=y, sr=sample_rate, n_mfcc=13, hop_length=hop)[1:]
    mfcc = mfcc / (np.linalg.norm(mfcc, axis=0, keepdims=True) + 1e-9)
    features = np.vstack([chroma, mfcc])
    features = features / (np.linalg.norm(features, axis=0, keepdims=True) + 1e-9)

    similarity = features.T @ features
    frames = similarity.shape[0]
    low = max(4, int(1.5 * sample_rate / hop))
    high = frames // 2
    if high - low < 12:
        return 0.0

    profile = np.array([np.mean(np.diagonal(similarity, lag))
                        for lag in range(low, high)])
    spread = np.std(profile)
    if spread < 1e-9:
        return 0.0
    profile = (profile - np.mean(profile)) / spread

    period = int(np.argmax(profile)) + low
    harmonics = [profile[k * period - low] for k in range(1, 5)
                 if low <= k * period < high]
    if len(harmonics) >= 2:
        return float(max(0.0, np.mean(harmonics)))
    # one strong recurrence with no second occurrence in range is partial evidence
    return float(max(0.0, profile[period - low] * 0.5))


def _beat_confidence(y: np.ndarray, sample_rate: int, tempo: float) -> float:
    """How much the beat tracker should be believed.

    `librosa.beat.beat_track` always returns a number. On material with no beat it
    returns its prior, and three of the six probe pieces came back at exactly the same
    117.5 BPM. A tempo that is really a default must not drive a storey count with the
    same authority as a measured one, so the regularity of the detected beats becomes the
    confidence, and the datum clamp does the rest.
    """
    if tempo <= 0:
        return 0.25
    _, beats = librosa.beat.beat_track(y=y, sr=sample_rate, units='time')
    if len(beats) < 6:
        return 0.3
    intervals = np.diff(beats)
    if intervals.size < 4 or np.mean(intervals) <= 0:
        return 0.3
    variation = float(np.std(intervals) / np.mean(intervals))
    # a metronomic pulse gives ~0.0; unstructured onsets give >0.5
    return float(min(0.9, max(0.25, 0.9 - variation * 1.3)))


def _timbre_variation(y: np.ndarray, sample_rate: int) -> float:
    """Mean pairwise distance between the timbral centroids of the segments.

    Repetition asks whether material returns; variation asks how far the material
    travels between sections. They are different measurements and must not share a
    source feature.
    """
    mfcc = librosa.feature.mfcc(y=y, sr=sample_rate, n_mfcc=13)
    if mfcc.shape[1] < SEGMENT_COUNT:
        return 0.0
    edges = np.linspace(0, mfcc.shape[1], SEGMENT_COUNT + 1, dtype=int)
    centroids = [mfcc[:, edges[i]:edges[i + 1]].mean(axis=1)
                 for i in range(SEGMENT_COUNT) if edges[i + 1] > edges[i]]
    if len(centroids) < 2:
        return 0.0
    distances = [
        float(np.linalg.norm(centroids[i] - centroids[j]))
        for i in range(len(centroids)) for j in range(i + 1, len(centroids))
    ]
    return float(np.mean(distances))


def _dynamic_range_db(y: np.ndarray) -> float:
    """The span between quiet and loud, in dB.

    A piece where one passage dominates has a hierarchy; one that sits at a constant
    level does not. This is the measurement, not the loudness itself.
    """
    frames = librosa.feature.rms(y=y)[0]
    frames = frames[frames > 1e-8]
    if frames.size < 8:
        return 0.0
    db = librosa.amplitude_to_db(frames, ref=float(np.max(frames)))
    return float(np.percentile(db, 97) - np.percentile(db, 5))


def _novelty_peak_rate(y: np.ndarray, sample_rate: int, duration: float) -> float:
    """Structural novelty peaks per minute.

    The onset envelope is smoothed hard so that beat-level activity drops out and only
    section boundaries survive. Density already measures beat-level activity; this
    measures how often the piece breaks.
    """
    envelope = librosa.onset.onset_strength(y=y, sr=sample_rate, aggregate=np.median)
    if envelope.size < 16:
        return 0.0
    window = max(4, envelope.size // 48)
    kernel = np.ones(window) / window
    smooth = np.convolve(envelope, kernel, mode='same')
    threshold = float(np.mean(smooth) + 1.2 * np.std(smooth))
    peaks = 0
    index = 1
    while index < smooth.size - 1:
        if smooth[index] > threshold and smooth[index] >= smooth[index - 1] \
                and smooth[index] > smooth[index + 1]:
            peaks += 1
            index += window
        else:
            index += 1
    return peaks / max(duration / 60.0, 1e-6)


def _harmonic_ratio(y: np.ndarray) -> float:
    """Harmonic energy share, from an HPSS split of the spectrogram."""
    spectrum = librosa.stft(y, n_fft=2048, hop_length=512)
    harmonic, percussive = librosa.decompose.hpss(spectrum)
    h = float(np.sum(np.abs(harmonic) ** 2))
    p = float(np.sum(np.abs(percussive) ** 2))
    return h / (h + p) if (h + p) > 0 else 0.0


def extract_audio_features(path: Path, original_filename: str) -> AudioFeatures:
    y, sample_rate = librosa.load(path, sr=TARGET_SAMPLE_RATE, mono=True)
    if y.size == 0:
        raise ValueError('The uploaded MP3 contains no decodable audio')

    duration = float(librosa.get_duration(y=y, sr=sample_rate))
    if duration < 1.0:
        raise ValueError('The uploaded MP3 must be at least one second long')

    peak = float(np.max(np.abs(y)))
    if peak < 1e-7:
        raise ValueError('The uploaded MP3 is effectively silent')

    tempo, _ = librosa.beat.beat_track(y=y, sr=sample_rate)
    tempo_bpm = _scalar(tempo)
    rms_energy = float(np.mean(librosa.feature.rms(y=y)))
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sample_rate)))
    onset_count = len(librosa.onset.onset_detect(y=y, sr=sample_rate, units='time'))
    onset_density = onset_count / duration

    periodicity = _periodicity(y, sample_rate)
    beat_confidence = _beat_confidence(y, sample_rate, tempo_bpm)
    variation = _timbre_variation(y, sample_rate)
    dynamic_range = _dynamic_range_db(y)
    novelty_rate = _novelty_peak_rate(y, sample_rate, duration)
    contrast = float(np.mean(librosa.feature.spectral_contrast(y=y, sr=sample_rate)))
    harmonic = _harmonic_ratio(y)
    flatness = float(np.mean(librosa.feature.spectral_flatness(y=y)))
    zero_crossing = float(np.mean(librosa.feature.zero_crossing_rate(y)))

    return AudioFeatures(
        provenance=AudioProvenance(
            filename=original_filename,
            sha256=_sha256(path),
            duration_seconds=round(duration, 4),
            sample_rate_hz=sample_rate,
            channels=1,
            extractor='librosa',
            extractor_version=f'{EXTRACTOR_VERSION}+librosa-{librosa.__version__}',
        ),
        tempo_bpm=_metric(
            tempo_bpm, 40.0, 220.0, 'bpm',
            'librosa.beat.beat_track with inter-beat regularity check',
            round(beat_confidence, 3)),
        rms_energy=_metric(
            rms_energy, 0.0, 0.564, 'rms',
            'librosa.feature.rms',
            0.95),
        onset_density_hz=_metric(
            onset_density, 0.0, 7.94, 'onsets_per_second',
            'librosa.onset.onset_detect',
            0.9),
        spectral_centroid_hz=_metric(
            centroid, 4.6052, 9.5429, 'hz',
            'librosa.feature.spectral_centroid',
            0.9,
            transform='log'),
        periodicity=_metric(
            periodicity, -0.8557, 2.0089, 'lag_comb_z',
            'harmonic comb of the chroma+timbre self-similarity lag profile',
            0.78,
            transform='log'),
        timbre_variation=_metric(
            variation, 0.0, 133.0, 'mfcc_distance',
            'mean pairwise MFCC centroid distance across segments',
            0.75),
        dynamic_range_db=_metric(
            dynamic_range, -0.6931, 5.0913, 'db',
            'RMS 97th minus 5th percentile in dB',
            0.80,
            transform='log'),
        novelty_peak_rate_per_min=_metric(
            novelty_rate, 0.0, 46.4, 'peaks_per_minute',
            'smoothed onset-strength novelty peaks',
            0.74),
        spectral_contrast_db=_metric(
            contrast, 2.9548, 3.3311, 'db',
            'librosa.feature.spectral_contrast',
            0.70,
            transform='log'),
        harmonic_ratio=_metric(
            harmonic, -3.8918, 6.0793, 'fraction',
            'HPSS harmonic energy share',
            0.68,
            transform='logit'),
        spectral_flatness=_metric(
            flatness, -11.5129, -0.3567, 'ratio',
            'librosa.feature.spectral_flatness',
            0.85,
            transform='log'),
        zero_crossing_rate=_metric(
            zero_crossing, -5.2933, 0.0, 'rate',
            'librosa.feature.zero_crossing_rate',
            0.88,
            transform='logit'),
        segments=_segment_features(y, sample_rate, duration),
    )