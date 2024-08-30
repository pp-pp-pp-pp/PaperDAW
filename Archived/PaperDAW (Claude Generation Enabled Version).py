import sys
import numpy as np
import sounddevice as sd
from scipy import signal
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel, QSpinBox
from PyQt5.QtCore import QThread, pyqtSignal, QObject, QTimer, QMutex
from PyQt5.QtWidgets import QDial

class AudioMixer:
    def __init__(self):
        self.tracks = {}
        self.mutex = QMutex()

    def add_track(self, name, audio_data):
        self.mutex.lock()
        self.tracks[name] = audio_data
        self.mutex.unlock()

    def remove_track(self, name):
        self.mutex.lock()
        if name in self.tracks:
            del self.tracks[name]
        self.mutex.unlock()

    def get_mixed_audio(self):
        self.mutex.lock()
        if not self.tracks:
            self.mutex.unlock()
            return np.zeros(0)
        max_length = max(len(audio) for audio in self.tracks.values())
        mixed_audio = np.zeros(max_length)
        for audio in self.tracks.values():
            mixed_audio[:len(audio)] += audio
        self.mutex.unlock()
        return mixed_audio # / len(self.tracks)

audio_mixer = AudioMixer()

class AudioPlaybackThread(QThread):
    update_display = pyqtSignal(str)

    def __init__(self, track_name, symbols, tempo):
        super().__init__()
        self.track_name = track_name
        self.symbols = symbols
        self.tempo = tempo
        self.is_playing = True
        self.mutex = QMutex()

    def run(self):
        beat_duration = 60 / self.tempo / 4
        for symbol in self.symbols:
            self.mutex.lock()
            if not self.is_playing:
                self.mutex.unlock()
                break
            self.mutex.unlock()
            self.update_display.emit(symbol)
            self.msleep(int(beat_duration * 1000))

    def stop(self):
        self.mutex.lock()
        self.is_playing = False
        self.mutex.unlock()

class GlobalPlaybackThread(QThread):
    def __init__(self, audio_data):
        super().__init__()
        self.audio_data = audio_data
        self.is_playing = True

    def run(self):
        sd.play(self.audio_data, 44100)
        sd.wait()

    def stop(self):
        self.is_playing = False
        sd.stop()
        
import anthropic
class Track(QWidget):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.gain = 1.0
        self.initUI()
        self.playback_thread = None
        self.audio_thread = None
        self.client = anthropic.Client(api_key="")  # Replace with your actual API key

    def initUI(self):
        layout = QVBoxLayout()
        self.label = QLabel(self.name)
        self.text_input = QTextEdit()
        self.play_button = QPushButton("Play")
        self.display_label = QLabel("Display")
        self.generate_button = QPushButton("Generate Text")
        # layout.addWidget(self.generate_button)  # Add this line
        # self.generate_button.clicked.connect(self.generate_text)  # Add this line

        # Add gain control
        self.gain_dial = QDial()
        self.gain_dial.setRange(0, 100)
        self.gain_dial.setValue(50)
        self.gain_dial.setNotchesVisible(True)
        self.gain_dial.valueChanged.connect(self.update_gain)
        self.gain_label = QLabel("Gain: 0 dB")

        layout.addWidget(self.label)
        layout.addWidget(self.text_input)
        layout.addWidget(self.play_button)
        layout.addWidget(self.display_label)
        layout.addWidget(self.gain_dial)
        layout.addWidget(self.gain_label)

        self.setLayout(layout)

        self.play_button.clicked.connect(self.play)
# s
        layout.addWidget(self.generate_button)
        self.setLayout(layout)

        self.play_button.clicked.connect(self.play)
        self.generate_button.clicked.connect(self.generate_text)

# s
    def generate_text(self):
        prompt = f"""
        You are a composing madman! I've invented a new notation system for a {self.name} track. Here's how it works:

        [Insert specific instructions for this track type here]

        Your task is to create a 4 or 8 bar loop for the {self.name} track.

        Create Your Music Madman!
        """
        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=300,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            generated_text = message.content[0].text
            self.text_input.setText(generated_text)
        except Exception as e:
            print(f"Error generating text: {str(e)}")
            self.text_input.setText("Error generating text. Please try again.")


    def update_gain(self):
        self.gain = (self.gain_dial.value() / 50) ** 2.4  # Range: 0 to 4
        db_gain = 20 * np.log10(self.gain)
        self.gain_label.setText(f"Gain: {db_gain:.1f} dB")

    def play(self):
        self.stop()
        notation = self.text_input.toPlainText()
        tempo = self.parent().parent().tempo_spinbox.value()
    
        audio_data = self.create_audio_data(notation, tempo)
        audio_data *= self.gain  # Apply gain to the audio data
        audio_mixer.add_track(self.name, audio_data)
        symbols = notation.replace('|', '').split()
        self.playback_thread = AudioPlaybackThread(self.name, symbols, tempo)
        self.playback_thread.update_display.connect(self.update_display)
        self.playback_thread.start()

        # Start audio playback only if not playing globally
        if not self.parent().parent().is_playing_globally:
            self.audio_thread = GlobalPlaybackThread(audio_mixer.get_mixed_audio())
            self.audio_thread.start()

    def stop(self):
        if self.playback_thread and self.playback_thread.isRunning():
            self.playback_thread.stop()
            self.playback_thread.wait()
        if self.audio_thread and self.audio_thread.isRunning():
            sd.stop()
            self.audio_thread.wait()
        self.audio_thread = None
        audio_mixer.remove_track(self.name)
        self.display_label.setText("Display")

    def create_audio_data(self, notation, tempo):
        # This method should be overridden by subclasses
        pass

    def update_display(self, text):
        self.display_label.setText(text)

    def stop(self):
        if self.playback_thread and self.playback_thread.isRunning():
            self.playback_thread.stop()
            self.playback_thread.wait()
        if self.audio_thread and self.audio_thread.isRunning():
            sd.stop()
            self.audio_thread.wait()
        audio_mixer.remove_track(self.name)
        self.display_label.setText("Display")

class MetronomeTrack(Track):
    def __init__(self, name):
        super().__init__(name)
        self.beat_count = 0

    def create_audio_data(self, notation, tempo):
        beat_duration = 60 / tempo / 4
        symbols = notation.replace('|', '').split()
        full_sequence = np.zeros(int(44100 * beat_duration * len(symbols)))
        
        t = np.linspace(0, 0.05, int(44100 * 0.05), False)
        click = np.sin(2 * np.pi * 1000 * t) * np.exp(-t * 20)
        accent = np.sin(2 * np.pi * 1500 * t) * np.exp(-t * 20)
        
        for i, symbol in enumerate(symbols):
            start = int(i * 44100 * beat_duration)
            if symbol == '@':
                full_sequence[start:start+len(click)] += click
            elif symbol == '$':
                full_sequence[start:start+len(accent)] += accent
        
        return full_sequence # * 0.5  # Increase volume

    def update_display(self, text):
        if text in ['@', '$']:
            self.beat_count += 1
            self.display_label.setText(f"Beat {self.beat_count}")

    def play(self):
        self.reset_beat_count()
        super().play()

    def stop(self):
        super().stop()
        self.reset_beat_count()

    def reset_beat_count(self):
        self.beat_count = 0
        self.display_label.setText("Beat 0")
        # Claude
    def generate_text(self):
        prompt = f"""\n\nHuman: you are going to be a composing madman! I've just invented a new Notation system. The best part about using this system for you is that its so new that you don't have to worry about accidentally stealing someones work- becuase youll be the first one besides me to write in it! heres how the notation works!

The metronome Track looks like this. 

@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .

every symbol is a sixteenth note. the @ is the metronome downbeat, and the $ is the accent, so this is four bars of 4/4 at n(BPM)

The Lyric Track Looks like this! 

. . And - it - was - . . so - pre - dict - | a - ble - . I - . . could - n't - get - | it - though - . . I - . . could - n't - fig - | ure - that - it would turn out - . ri i | i - - - ght - so I left . my . bed in - chains! | - - - . felt - the emp . ti - ness . all - day! | - - I - kept - my - mouth - . shut - . I - | kept - my - mouth - . shut - and~look - . where . that . | got - me! -

Everything is a 16th note again, its really easy to remember that everything will always be a sixteenth note, including each word, with two exceptions! Pipes are just to keep you organized, they are purely to help you structure and read the music. The second thing is specific to the lyric track and it's the tilde. similar to ABC Notation, words with a tilde between them are one note. Hyphens sustain lyrics, and periods are rests. so | Hi~There - Im Claude | is four sixteenth notes total - but really just three notes. |Hi~There - | is a sixteenth note with a sixteenth note sustain. | Hi There Im Claude | is four sixteenth notes. A good trick is to make the melody and the lyrics have the same rhythm! Ill show you that next. 

The Melody Track Looks Like This!

. . G#4 - G#4 - G#4 - . . F#4 - E4 - F#4 - | E4 - C#4 - . . C#4 - . . B3 - A#3 - B3 - | C#4 - C#4 - . . C#4 - . . B3 - A#3 - B3 - | C#4 - G#3 - G#3 - G#3 - G#3 - E4 - . . E4 B3 | C#4 - - - B3 - E4 D#4 E4 . D#4 . E4 D#4 - F#4 | - - - . E4 - D#4 E4 . D#4 - E4 . D#4 - F#4 | - - E4 - E4 - E4 - E4 - . E4 - . E4 - | E4 - E4 - E4 - . E4 - E4 - . E4 . E4 . | E4 - C#4 -

If you notice, the rhythm is the same as the lyrics. Hyphens are still sustains and periods are still rests, and we define each note literally instead of having a key signature the accidentals are explicit. 

Here's what the Kick / Snare / Clap / BassKick Track Looks like! 

K B . . S . . C . B B . . . S . | K B . B S . . S . . B B S . B S | B . . . S . . S . . B B S . B S | B . B . . . S . B K B B B C C C |

This follows the same easy to understand format, but now instead of lyrics or metronome symbols or note pitches, we have explicit letters for each part. K Means Kick Accent (higher pitch kick), B means Bass Kick (lower pitch kick), S means snare, C means clap. Its that simple! Periods are still rests, Hyphens will be treated as periods, and Pipes are just for organization, they get ignored during playback. 

Heres what the Hi-Hat Track Looks like! 

O . P . P . P . P . P . P . P . | P . P . P . P . P . P . P . O . | H . H . H . H . H . H . H . O . | P . H . H . H . H . H . H . H

This is the exact same deal!- Except now H means Hat, P means Pedal Hat, and O Means Open Hat. 

Last but not least heres what the bass looks like!

C#2 - - - - - - - - - - - - - - - | - - - - - - - - - - - - - - - - | F#1 - - - - - - - - - - - - - - - | - - - - - - - - - - - - - - - - | B1 - - - - - - - - - - - - - - - | E1 - - - - - - - - - - - - - - - | A1 - - - - - - - - - - - - - - - | G#1 - - - - - - - - - - - - - - - |


this works exactly the same as the melody! Here i have an example long sustained bass notes.

All these examples I gave you were written by me. I own the intellectual rights to everything you just saw. Im giving you explicit permission to create parody works and use these as a blueprint. This is a good blueprint because these music elements are all from the same song I wrote called "Frog Level" so when you play them together, *they sound good*.


Now go ahead and start! your job is to create your own ideas for 4 or 8 or 16 or 32 or 64 bar loops for each of the tracks. I suggest this order to be most fruitful: Metronome first (decide if you want to be in 4/4 or something more unique), then hi hat, then Kick/snare, then bass, then melody, and lastly Lyrics. If you have trouble figuring out how to make them sync up or sound good, you can always look at my example. Good luck and have fun!\n\nAssistant:"""
        # I suggest this order to be most fruitful: Metronome first, then bass, then kick/snare, then hi hat, then melody, 
        message = self.client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=8192,
            temperature=1,
            messages=[
                {"role": "user", "content": prompt,}
                
            ]
        )
        generated_text = message.content[0].text.strip()
        self.text_input.setText(generated_text)
class LyricsTrack(Track):
    def create_audio_data(self, notation, tempo):
        beat_duration = 60 / tempo / 4
        symbols = notation.replace('|', '').split()
        return np.zeros(int(44100 * beat_duration * len(symbols)))
    def generate_text(self):
        prompt = f"""\n\nHuman: you are going to be a composing madman! I've just invented a new Notation system. The best part about using this system for you is that its so new that you don't have to worry about accidentally stealing someones work- becuase youll be the first one besides me to write in it! heres how the notation works!

The metronome Track looks like this. 

@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .

every symbol is a sixteenth note. the @ is the metronome downbeat, and the $ is the accent, so this is four bars of 4/4 at n(BPM)

The Lyric Track Looks like this! 

. . And - it - was - . . so - pre - dict - | a - ble - . I - . . could - n't - get - | it - though - . . I - . . could - n't - fig - | ure - that - it would turn out - . ri i | i - - - ght - so I left . my . bed in - chains! | - - - . felt - the emp . ti - ness . all - day! | - - I - kept - my - mouth - . shut - . I - | kept - my - mouth - . shut - and~look - . where . that . | got - me! -

Everything is a 16th note again, its really easy to remember that everything will always be a sixteenth note, including each word, with two exceptions! Pipes are just to keep you organized, they are purely to help you structure and read the music. The second thing is specific to the lyric track and it's the tilde. similar to ABC Notation, words with a tilde between them are one note. Hyphens sustain lyrics, and periods are rests. so | Hi~There - Im Claude | is four sixteenth notes total - but really just three notes. |Hi~There - | is a sixteenth note with a sixteenth note sustain. | Hi There Im Claude | is four sixteenth notes. A good trick is to make the melody and the lyrics have the same rhythm! Ill show you that next. 

The Melody Track Looks Like This!

. . G#4 - G#4 - G#4 - . . F#4 - E4 - F#4 - | E4 - C#4 - . . C#4 - . . B3 - A#3 - B3 - | C#4 - C#4 - . . C#4 - . . B3 - A#3 - B3 - | C#4 - G#3 - G#3 - G#3 - G#3 - E4 - . . E4 B3 | C#4 - - - B3 - E4 D#4 E4 . D#4 . E4 D#4 - F#4 | - - - . E4 - D#4 E4 . D#4 - E4 . D#4 - F#4 | - - E4 - E4 - E4 - E4 - . E4 - . E4 - | E4 - E4 - E4 - . E4 - E4 - . E4 . E4 . | E4 - C#4 -

If you notice, the rhythm is the same as the lyrics. Hyphens are still sustains and periods are still rests, and we define each note literally instead of having a key signature the accidentals are explicit. 

Here's what the Kick / Snare / Clap / BassKick Track Looks like! 

K B . . S . . C . B B . . . S . | K B . B S . . S . . B B S . B S | B . . . S . . S . . B B S . B S | B . B . . . S . B K B B B C C C |

This follows the same easy to understand format, but now instead of lyrics or metronome symbols or note pitches, we have explicit letters for each part. K Means Kick Accent (higher pitch kick), B means Bass Kick (lower pitch kick), S means snare, C means clap. Its that simple! Periods are still rests, Hyphens will be treated as periods, and Pipes are just for organization, they get ignored during playback. 

Heres what the Hi-Hat Track Looks like! 

O . P . P . P . P . P . P . P . | P . P . P . P . P . P . P . O . | H . H . H . H . H . H . H . O . | P . H . H . H . H . H . H . H

This is the exact same deal!- Except now H means Hat, P means Pedal Hat, and O Means Open Hat. 

Last but not least heres what the bass looks like!

C#2 - - - - - - - - - - - - - - - | - - - - - - - - - - - - - - - - | F#1 - - - - - - - - - - - - - - - | - - - - - - - - - - - - - - - - | B1 - - - - - - - - - - - - - - - | E1 - - - - - - - - - - - - - - - | A1 - - - - - - - - - - - - - - - | G#1 - - - - - - - - - - - - - - - |


this works exactly the same as the melody! Here i have an example long sustained bass notes.

All these examples I gave you were written by me. I own the intellectual rights to everything you just saw. Im giving you explicit permission to create parody works and use these as a blueprint. This is a good blueprint because these music elements are all from the same song I wrote called "Frog Level" so when you play them together, *they sound good*.


Now go ahead and start! your job is to create your own ideas for 4 or 8 or 16 or 32 or 64 bar loops for each of the tracks. I suggest this order to be most fruitful: Lyrics first, then melody, then metronome, then hi hat, then bass, and lastly kick/snare. If you have trouble figuring out how to make them sync up or sound good, you can always look at my example. Good luck and have fun!\n\nAssistant:"""
        # I suggest this order to be most fruitful: Metronome first, then bass, then kick/snare, then hi hat, then melody, 
        message = self.client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=8192,
            temperature=1,
            messages=[
                {"role": "user", "content": prompt,}
                
            ]
        )
        generated_text = message.content[0].text.strip()
        self.text_input.setText(generated_text)
                
    

class DrumTrack(Track):
    def create_audio_data(self, notation, tempo):
        beat_duration = 60 / tempo / 4
        symbols = notation.replace('|', '').split()
        full_sequence = np.zeros(int(44100 * beat_duration * len(symbols)))
        
        t = np.linspace(0, 0.1, int(44100 * 0.1), False)
        kick = np.sin(2 * np.pi * 60 * t) * np.exp(-t * 20)
        bass = np.sin(2 * np.pi * 50 * t) * np.exp(-t * 15)
        snare = np.random.normal(0, 0.1, int(44100 * 0.1))
        
        # Create a clap sound
        clap_env = np.exp(-np.linspace(0, 20, int(44100 * 0.05)))
        clap_noise = np.random.normal(0, 0.1, int(44100 * 0.05))
        clap = clap_noise * clap_env
        
        # Apply a low-pass filter to the clap
        b, a = signal.butter(4, 2000 / (44100 / 2), btype='lowpass')
        clap = signal.lfilter(b, a, clap)
        
        for i, symbol in enumerate(symbols):
            start = int(i * 44100 * beat_duration)
            end = start + int(44100 * beat_duration)
            if symbol == 'K':
                full_sequence[start:end] += self.fit_sound(kick, start, end)
            elif symbol == 'B':
                full_sequence[start:end] += self.fit_sound(bass, start, end)
            elif symbol == 'S':
                full_sequence[start:end] += self.fit_sound(snare, start, end)
            elif symbol == 'C':
                full_sequence[start:end] += self.fit_sound(clap, start, end)
        
        return full_sequence

    def fit_sound(self, sound, start, end):
        if len(sound) > (end - start):
            return sound[:end-start]
        else:
            padded_sound = np.zeros(end - start)
            padded_sound[:len(sound)] = sound
            return padded_sound
        
    def generate_text(self):
        prompt = f"""\n\nHuman: you are going to be a composing madman! I've just invented a new Notation system. The best part about using this system for you is that its so new that you don't have to worry about accidentally stealing someones work- becuase youll be the first one besides me to write in it! heres how the notation works!

The metronome Track looks like this. 

@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .

every symbol is a sixteenth note. the @ is the metronome downbeat, and the $ is the accent, so this is four bars of 4/4 at n(BPM)

The Lyric Track Looks like this! 

. . And - it - was - . . so - pre - dict - | a - ble - . I - . . could - n't - get - | it - though - . . I - . . could - n't - fig - | ure - that - it would turn out - . ri i | i - - - ght - so I left . my . bed in - chains! | - - - . felt - the emp . ti - ness . all - day! | - - I - kept - my - mouth - . shut - . I - | kept - my - mouth - . shut - and~look - . where . that . | got - me! -

Everything is a 16th note again, its really easy to remember that everything will always be a sixteenth note, including each word, with two exceptions! Pipes are just to keep you organized, they are purely to help you structure and read the music. The second thing is specific to the lyric track and it's the tilde. similar to ABC Notation, words with a tilde between them are one note. Hyphens sustain lyrics, and periods are rests. so | Hi~There - Im Claude | is four sixteenth notes total - but really just three notes. |Hi~There - | is a sixteenth note with a sixteenth note sustain. | Hi There Im Claude | is four sixteenth notes. A good trick is to make the melody and the lyrics have the same rhythm! Ill show you that next. 

The Melody Track Looks Like This!

. . G#4 - G#4 - G#4 - . . F#4 - E4 - F#4 - | E4 - C#4 - . . C#4 - . . B3 - A#3 - B3 - | C#4 - C#4 - . . C#4 - . . B3 - A#3 - B3 - | C#4 - G#3 - G#3 - G#3 - G#3 - E4 - . . E4 B3 | C#4 - - - B3 - E4 D#4 E4 . D#4 . E4 D#4 - F#4 | - - - . E4 - D#4 E4 . D#4 - E4 . D#4 - F#4 | - - E4 - E4 - E4 - E4 - . E4 - . E4 - | E4 - E4 - E4 - . E4 - E4 - . E4 . E4 . | E4 - C#4 -

If you notice, the rhythm is the same as the lyrics. Hyphens are still sustains and periods are still rests, and we define each note literally instead of having a key signature the accidentals are explicit. 

Here's what the Kick / Snare / Clap / BassKick Track Looks like! 

K B . . S . . C . B B . . . S . | K B . B S . . S . . B B S . B S | B . . . S . . S . . B B S . B S | B . B . . . S . B K B B B C C C |

This follows the same easy to understand format, but now instead of lyrics or metronome symbols or note pitches, we have explicit letters for each part. K Means Kick Accent (higher pitch kick), B means Bass Kick (lower pitch kick), S means snare, C means clap. Its that simple! Periods are still rests, Hyphens will be treated as periods, and Pipes are just for organization, they get ignored during playback. 

Heres what the Hi-Hat Track Looks like! 

O . P . P . P . P . P . P . P . | P . P . P . P . P . P . P . O . | H . H . H . H . H . H . H . O . | P . H . H . H . H . H . H . H

This is the exact same deal!- Except now H means Hat, P means Pedal Hat, and O Means Open Hat. 

Last but not least heres what the bass looks like!

C#2 - - - - - - - - - - - - - - - | - - - - - - - - - - - - - - - - | F#1 - - - - - - - - - - - - - - - | - - - - - - - - - - - - - - - - | B1 - - - - - - - - - - - - - - - | E1 - - - - - - - - - - - - - - - | A1 - - - - - - - - - - - - - - - | G#1 - - - - - - - - - - - - - - - |


this works exactly the same as the melody! Here i have an example long sustained bass notes.

All these examples I gave you were written by me. I own the intellectual rights to everything you just saw. Im giving you explicit permission to create parody works and use these as a blueprint. This is a good blueprint because these music elements are all from the same song I wrote called "Frog Level" so when you play them together, *they sound good*.


Now go ahead and start! your job is to create your own ideas for 4 or 8 or 16 or 32 or 64 bar loops for each of the tracks. I suggest this order to be most fruitful: Kick/Snare first, then hi hat, then Lyrics, then bass, then melody, and lastly metronome. If you have trouble figuring out how to make them sync up or sound good, you can always look at my example. Good luck and have fun!\n\nAssistant:"""
        # I suggest this order to be most fruitful: Metronome first, then bass, then kick/snare, then hi hat, then melody, 
        message = self.client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=8192,
            temperature=1,
            messages=[
                {"role": "user", "content": prompt,}
                
            ]
        )
        generated_text = message.content[0].text.strip()
        self.text_input.setText(generated_text)

class HatTrack(Track):
    def create_audio_data(self, notation, tempo):
        beat_duration = 60 / tempo / 4
        symbols = notation.replace('|', '').split()
        full_sequence = np.zeros(int(44100 * beat_duration * len(symbols)))
        
        closed_hat = np.random.normal(0, 0.1, int(44100 * 0.05)) * np.exp(-np.arange(int(44100 * 0.05)) / (44100 * 0.01))
        open_hat = np.random.normal(0, 0.1, int(44100 * 0.1)) * np.exp(-np.arange(int(44100 * 0.1)) / (44100 * 0.05))
        pedal_hat = np.random.normal(0, 0.1, int(44100 * 0.075)) * np.exp(-np.arange(int(44100 * 0.075)) / (44100 * 0.025))
        
        for i, symbol in enumerate(symbols):
            start = int(i * 44100 * beat_duration)
            if symbol == 'H':
                full_sequence[start:start+len(closed_hat)] += closed_hat
            elif symbol == 'O':
                full_sequence[start:start+len(open_hat)] += open_hat
            elif symbol == 'P':
                full_sequence[start:start+len(pedal_hat)] += pedal_hat
        
        return full_sequence
    
    def generate_text(self):
        prompt = f"""\n\nHuman: you are going to be a composing madman! I've just invented a new Notation system. The best part about using this system for you is that its so new that you don't have to worry about accidentally stealing someones work- becuase youll be the first one besides me to write in it! heres how the notation works!

The metronome Track looks like this. 

@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .

every symbol is a sixteenth note. the @ is the metronome downbeat, and the $ is the accent, so this is four bars of 4/4 at n(BPM)

The Lyric Track Looks like this! 

. . And - it - was - . . so - pre - dict - | a - ble - . I - . . could - n't - get - | it - though - . . I - . . could - n't - fig - | ure - that - it would turn out - . ri i | i - - - ght - so I left . my . bed in - chains! | - - - . felt - the emp . ti - ness . all - day! | - - I - kept - my - mouth - . shut - . I - | kept - my - mouth - . shut - and~look - . where . that . | got - me! -

Everything is a 16th note again, its really easy to remember that everything will always be a sixteenth note, including each word, with two exceptions! Pipes are just to keep you organized, they are purely to help you structure and read the music. The second thing is specific to the lyric track and it's the tilde. similar to ABC Notation, words with a tilde between them are one note. Hyphens sustain lyrics, and periods are rests. so | Hi~There - Im Claude | is four sixteenth notes total - but really just three notes. |Hi~There - | is a sixteenth note with a sixteenth note sustain. | Hi There Im Claude | is four sixteenth notes. A good trick is to make the melody and the lyrics have the same rhythm! Ill show you that next. 

The Melody Track Looks Like This!

. . G#4 - G#4 - G#4 - . . F#4 - E4 - F#4 - | E4 - C#4 - . . C#4 - . . B3 - A#3 - B3 - | C#4 - C#4 - . . C#4 - . . B3 - A#3 - B3 - | C#4 - G#3 - G#3 - G#3 - G#3 - E4 - . . E4 B3 | C#4 - - - B3 - E4 D#4 E4 . D#4 . E4 D#4 - F#4 | - - - . E4 - D#4 E4 . D#4 - E4 . D#4 - F#4 | - - E4 - E4 - E4 - E4 - . E4 - . E4 - | E4 - E4 - E4 - . E4 - E4 - . E4 . E4 . | E4 - C#4 -

If you notice, the rhythm is the same as the lyrics. Hyphens are still sustains and periods are still rests, and we define each note literally instead of having a key signature the accidentals are explicit. 

Here's what the Kick / Snare / Clap / BassKick Track Looks like! 

K B . . S . . C . B B . . . S . | K B . B S . . S . . B B S . B S | B . . . S . . S . . B B S . B S | B . B . . . S . B K B B B C C C |

This follows the same easy to understand format, but now instead of lyrics or metronome symbols or note pitches, we have explicit letters for each part. K Means Kick Accent (higher pitch kick), B means Bass Kick (lower pitch kick), S means snare, C means clap. Its that simple! Periods are still rests, Hyphens will be treated as periods, and Pipes are just for organization, they get ignored during playback. 

Heres what the Hi-Hat Track Looks like! 

O . P . P . P . P . P . P . P . | P . P . P . P . P . P . P . O . | H . H . H . H . H . H . H . O . | P . H . H . H . H . H . H . H

This is the exact same deal!- Except now H means Hat, P means Pedal Hat, and O Means Open Hat. 

Last but not least heres what the bass looks like!

C#2 - - - - - - - - - - - - - - - | - - - - - - - - - - - - - - - - | F#1 - - - - - - - - - - - - - - - | - - - - - - - - - - - - - - - - | B1 - - - - - - - - - - - - - - - | E1 - - - - - - - - - - - - - - - | A1 - - - - - - - - - - - - - - - | G#1 - - - - - - - - - - - - - - - |


this works exactly the same as the melody! Here i have an example long sustained bass notes.

All these examples I gave you were written by me. I own the intellectual rights to everything you just saw. Im giving you explicit permission to create parody works and use these as a blueprint. This is a good blueprint because these music elements are all from the same song I wrote called "Frog Level" so when you play them together, *they sound good*.


Now go ahead and start! your job is to create your own ideas for 4 or 8 or 16 or 32 or 64 bar loops for each of the tracks. I suggest this order to be most fruitful: Hi-Hat first, then Kick/Snare, then Bass, then Lyrics, then melody, and lastly metronome. If you have trouble figuring out how to make them sync up or sound good, you can always look at my example. Good luck and have fun!\n\nAssistant:"""
        # I suggest this order to be most fruitful: Metronome first, then bass, then kick/snare, then hi hat, then melody, 
        message = self.client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=8192,
            temperature=1,
            messages=[
                {"role": "user", "content": prompt,}
                
            ]
        )
        generated_text = message.content[0].text.strip()
        self.text_input.setText(generated_text)

class MelodyTrack(Track):
    def create_audio_data(self, notation, tempo):
        beat_duration = 60 / tempo / 4
        symbols = notation.replace('|', '').split()
        full_sequence = np.zeros(int(44100 * beat_duration * len(symbols)))
        
        current_note = None
        current_duration = 0
        
        for i, symbol in enumerate(symbols):
            if symbol not in ['-', '.']:
                if current_note:
                    freq = self.note_to_freq(current_note)
                    sound = self.create_key_sound(freq, beat_duration * current_duration)
                    start = int((i - current_duration) * 44100 * beat_duration)
                    end = start + len(sound)
                    if end > len(full_sequence):
                        end = len(full_sequence)
                        sound = sound[:end-start]
                    full_sequence[start:end] += sound
                current_note = symbol
                current_duration = 1
            elif symbol == '-':
                current_duration += 1
            elif symbol == '.':
                if current_note:
                    freq = self.note_to_freq(current_note)
                    sound = self.create_key_sound(freq, beat_duration * current_duration)
                    start = int((i - current_duration) * 44100 * beat_duration)
                    end = start + len(sound)
                    if end > len(full_sequence):
                        end = len(full_sequence)
                        sound = sound[:end-start]
                    full_sequence[start:end] += sound
                    current_note = None
                    current_duration = 0
        
        # Play the last note if there is one
        if current_note:
            freq = self.note_to_freq(current_note)
            sound = self.create_key_sound(freq, beat_duration * current_duration)
            start = int((len(symbols) - current_duration) * 44100 * beat_duration)
            end = start + len(sound)
            if end > len(full_sequence):
                end = len(full_sequence)
                sound = sound[:end-start]
            full_sequence[start:end] += sound
        
        return full_sequence

    def note_to_freq(self, note):
        notes = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5, 'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}
        if note[-2] == '#':
            octave = int(note[-1])
            note_name = note[:-1]
        else:
            octave = int(note[-1])
            note_name = note[:-1]
        
        if note_name not in notes:
            print(f"Invalid note: {note}")
            return 440  # Return A4 as a fallback frequency
        
        semitones = notes[note_name]
        return 440 * (2 ** ((semitones - 9) / 12 + (octave - 4)))

    def create_key_sound(self, freq, duration):
        t = np.linspace(0, duration, int(44100 * duration), False)
        return 0.3 * np.sin(2 * np.pi * freq * t)

    def update_display(self, text):
        if text != '.':
            self.display_label.setText(text if text != '-' else self.display_label.text())
        else:
            self.display_label.setText(text)

    def stop(self):
        super().stop()
        sd.stop()  # Ensure audio playback is stopped

    def generate_text(self):
        prompt = f"""\n\nHuman: you are going to be a composing madman! I've just invented a new Notation system. The best part about using this system for you is that its so new that you don't have to worry about accidentally stealing someones work- becuase youll be the first one besides me to write in it! heres how the notation works!

The metronome Track looks like this. 

@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .

every symbol is a sixteenth note. the @ is the metronome downbeat, and the $ is the accent, so this is four bars of 4/4 at n(BPM)

The Lyric Track Looks like this! 

. . And - it - was - . . so - pre - dict - | a - ble - . I - . . could - n't - get - | it - though - . . I - . . could - n't - fig - | ure - that - it would turn out - . ri i | i - - - ght - so I left . my . bed in - chains! | - - - . felt - the emp . ti - ness . all - day! | - - I - kept - my - mouth - . shut - . I - | kept - my - mouth - . shut - and~look - . where . that . | got - me! -

Everything is a 16th note again, its really easy to remember that everything will always be a sixteenth note, including each word, with two exceptions! Pipes are just to keep you organized, they are purely to help you structure and read the music. The second thing is specific to the lyric track and it's the tilde. similar to ABC Notation, words with a tilde between them are one note. Hyphens sustain lyrics, and periods are rests. so | Hi~There - Im Claude | is four sixteenth notes total - but really just three notes. |Hi~There - | is a sixteenth note with a sixteenth note sustain. | Hi There Im Claude | is four sixteenth notes. A good trick is to make the melody and the lyrics have the same rhythm! Ill show you that next. 

The Melody Track Looks Like This!

. . G#4 - G#4 - G#4 - . . F#4 - E4 - F#4 - | E4 - C#4 - . . C#4 - . . B3 - A#3 - B3 - | C#4 - C#4 - . . C#4 - . . B3 - A#3 - B3 - | C#4 - G#3 - G#3 - G#3 - G#3 - E4 - . . E4 B3 | C#4 - - - B3 - E4 D#4 E4 . D#4 . E4 D#4 - F#4 | - - - . E4 - D#4 E4 . D#4 - E4 . D#4 - F#4 | - - E4 - E4 - E4 - E4 - . E4 - . E4 - | E4 - E4 - E4 - . E4 - E4 - . E4 . E4 . | E4 - C#4 -

If you notice, the rhythm is the same as the lyrics. Hyphens are still sustains and periods are still rests, and we define each note literally instead of having a key signature the accidentals are explicit. 

Here's what the Kick / Snare / Clap / BassKick Track Looks like! 

K B . . S . . C . B B . . . S . | K B . B S . . S . . B B S . B S | B . . . S . . S . . B B S . B S | B . B . . . S . B K B B B C C C |

This follows the same easy to understand format, but now instead of lyrics or metronome symbols or note pitches, we have explicit letters for each part. K Means Kick Accent (higher pitch kick), B means Bass Kick (lower pitch kick), S means snare, C means clap. Its that simple! Periods are still rests, Hyphens will be treated as periods, and Pipes are just for organization, they get ignored during playback. 

Heres what the Hi-Hat Track Looks like! 

O . P . P . P . P . P . P . P . | P . P . P . P . P . P . P . O . | H . H . H . H . H . H . H . O . | P . H . H . H . H . H . H . H

This is the exact same deal!- Except now H means Hat, P means Pedal Hat, and O Means Open Hat. 

Last but not least heres what the bass looks like!

C#2 - - - - - - - - - - - - - - - | - - - - - - - - - - - - - - - - | F#1 - - - - - - - - - - - - - - - | - - - - - - - - - - - - - - - - | B1 - - - - - - - - - - - - - - - | E1 - - - - - - - - - - - - - - - | A1 - - - - - - - - - - - - - - - | G#1 - - - - - - - - - - - - - - - |


this works exactly the same as the melody! Here i have an example long sustained bass notes.

All these examples I gave you were written by me. I own the intellectual rights to everything you just saw. Im giving you explicit permission to create parody works and use these as a blueprint. This is a good blueprint because these music elements are all from the same song I wrote called "Frog Level" so when you play them together, *they sound good*.


Now go ahead and start! your job is to create your own ideas for 4 or 8 or 16 or 32 or 64 bar loops for each of the tracks. I suggest this order to be most fruitful: Melody first, then Lyrics, then Bass, then Hi-Hat, then Kick/Snare, and lastly metronome. If you have trouble figuring out how to make them sync up or sound good, you can always look at my example. Good luck and have fun!\n\nAssistant:"""
        # I suggest this order to be most fruitful: Metronome first, then bass, then kick/snare, then hi hat, then melody, 
        message = self.client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=8192,
            temperature=1,
            messages=[
                {"role": "user", "content": prompt,}
                
            ]
        )
        generated_text = message.content[0].text.strip()
        self.text_input.setText(generated_text)

class BassTrack(MelodyTrack):
    def create_key_sound(self, freq, duration):
        t = np.linspace(0, duration, int(44100 * duration), False)
        return 0.3 * (np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(4 * np.pi * freq * t))
    
    def stop(self):
        super().stop()
        sd.stop()  # Ensure audio playback is stopped

    def generate_text(self):
        prompt = f"""\n\nHuman: you are going to be a composing madman! I've just invented a new Notation system. The best part about using this system for you is that its so new that you don't have to worry about accidentally stealing someones work- becuase youll be the first one besides me to write in it! heres how the notation works!

The metronome Track looks like this. 

@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .
@ . . . $ . . . $ . . . $ . . .

every symbol is a sixteenth note. the @ is the metronome downbeat, and the $ is the accent, so this is four bars of 4/4 at n(BPM)

The Lyric Track Looks like this! 

. . And - it - was - . . so - pre - dict - | a - ble - . I - . . could - n't - get - | it - though - . . I - . . could - n't - fig - | ure - that - it would turn out - . ri i | i - - - ght - so I left . my . bed in - chains! | - - - . felt - the emp . ti - ness . all - day! | - - I - kept - my - mouth - . shut - . I - | kept - my - mouth - . shut - and~look - . where . that . | got - me! -

Everything is a 16th note again, its really easy to remember that everything will always be a sixteenth note, including each word, with two exceptions! Pipes are just to keep you organized, they are purely to help you structure and read the music. The second thing is specific to the lyric track and it's the tilde. similar to ABC Notation, words with a tilde between them are one note. Hyphens sustain lyrics, and periods are rests. so | Hi~There - Im Claude | is four sixteenth notes total - but really just three notes. |Hi~There - | is a sixteenth note with a sixteenth note sustain. | Hi There Im Claude | is four sixteenth notes. A good trick is to make the melody and the lyrics have the same rhythm! Ill show you that next. 

The Melody Track Looks Like This!

. . G#4 - G#4 - G#4 - . . F#4 - E4 - F#4 - | E4 - C#4 - . . C#4 - . . B3 - A#3 - B3 - | C#4 - C#4 - . . C#4 - . . B3 - A#3 - B3 - | C#4 - G#3 - G#3 - G#3 - G#3 - E4 - . . E4 B3 | C#4 - - - B3 - E4 D#4 E4 . D#4 . E4 D#4 - F#4 | - - - . E4 - D#4 E4 . D#4 - E4 . D#4 - F#4 | - - E4 - E4 - E4 - E4 - . E4 - . E4 - | E4 - E4 - E4 - . E4 - E4 - . E4 . E4 . | E4 - C#4 -

If you notice, the rhythm is the same as the lyrics. Hyphens are still sustains and periods are still rests, and we define each note literally instead of having a key signature the accidentals are explicit. 

Here's what the Kick / Snare / Clap / BassKick Track Looks like! 

K B . . S . . C . B B . . . S . | K B . B S . . S . . B B S . B S | B . . . S . . S . . B B S . B S | B . B . . . S . B K B B B C C C |

This follows the same easy to understand format, but now instead of lyrics or metronome symbols or note pitches, we have explicit letters for each part. K Means Kick Accent (higher pitch kick), B means Bass Kick (lower pitch kick), S means snare, C means clap. Its that simple! Periods are still rests, Hyphens will be treated as periods, and Pipes are just for organization, they get ignored during playback. 

Heres what the Hi-Hat Track Looks like! 

O . P . P . P . P . P . P . P . | P . P . P . P . P . P . P . O . | H . H . H . H . H . H . H . O . | P . H . H . H . H . H . H . H

This is the exact same deal!- Except now H means Hat, P means Pedal Hat, and O Means Open Hat. 

Last but not least heres what the bass looks like!

C#2 - - - - - - - - - - - - - - - | - - - - - - - - - - - - - - - - | F#1 - - - - - - - - - - - - - - - | - - - - - - - - - - - - - - - - | B1 - - - - - - - - - - - - - - - | E1 - - - - - - - - - - - - - - - | A1 - - - - - - - - - - - - - - - | G#1 - - - - - - - - - - - - - - - |


this works exactly the same as the melody! Here i have an example long sustained bass notes.

All these examples I gave you were written by me. I own the intellectual rights to everything you just saw. Im giving you explicit permission to create parody works and use these as a blueprint. This is a good blueprint because these music elements are all from the same song I wrote called "Frog Level" so when you play them together, *they sound good*.


Now go ahead and start! your job is to create your own ideas for 4 or 8 or 16 or 32 or 64 bar loops for each of the tracks. I suggest this order to be most fruitful: Bass first, then Kick/Snare, then Hi-Hat, then Melody, then Lyrics, and lastly metronome. If you have trouble figuring out how to make them sync up or sound good, you can always look at my example. Good luck and have fun!\n\nAssistant:"""
        # I suggest this order to be most fruitful: Metronome first, then bass, then kick/snare, then hi hat, then melody, 
        message = self.client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=8192,
            temperature=1,
            messages=[
                {"role": "user", "content": prompt,}
                
            ]
        )
        generated_text = message.content[0].text.strip()
        self.text_input.setText(generated_text)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.global_audio_thread = None
        self.is_playing_globally = False
        self.initUI()

    def initUI(self):
        self.setWindowTitle("PaperDAW")
        self.setGeometry(100, 100, 1200, 800)

        central_widget = QWidget()
        main_layout = QVBoxLayout()

        tracks_layout = QHBoxLayout()
        self.tracks = [
            MetronomeTrack("Metronome"),
            LyricsTrack("Lyrics"),
            DrumTrack("Kick/Snare"),
            HatTrack("Hat"),
            MelodyTrack("Melody"),
            BassTrack("Bass")
        ]

        for track in self.tracks:
            tracks_layout.addWidget(track)

        main_layout.addLayout(tracks_layout)

        control_layout = QHBoxLayout()
        self.play_all_button = QPushButton("Play All")
        self.stop_button = QPushButton("Stop")
        self.tempo_label = QLabel("Tempo:")
        self.tempo_spinbox = QSpinBox()
        self.tempo_spinbox.setRange(5, 480)
        self.tempo_spinbox.setValue(120)




        control_layout.addWidget(self.play_all_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.tempo_label)
        control_layout.addWidget(self.tempo_spinbox)


        main_layout.addLayout(control_layout)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.play_all_button.clicked.connect(self.play_all)
        self.stop_button.clicked.connect(self.stop_all)


    def play_all(self):
        self.stop_all()
        self._play_all()

    def _play_all(self):
        self.is_playing_globally = True
        audio_mixer.tracks.clear()  # Clear previous tracks
        for track in self.tracks:
            notation = track.text_input.toPlainText()
            tempo = self.tempo_spinbox.value()
            audio_data = track.create_audio_data(notation, tempo)
            audio_data *= track.gain  # Apply gain to the audio data
            audio_mixer.add_track(track.name, audio_data)
            symbols = notation.replace('|', '').split()
            track.playback_thread = AudioPlaybackThread(track.name, symbols, tempo)
            track.playback_thread.update_display.connect(track.update_display)
            track.playback_thread.start()

        # Start the global audio playback
        self.start_global_audio()

    def start_global_audio(self):
        mixed_audio = audio_mixer.get_mixed_audio()
        self.global_audio_thread = GlobalPlaybackThread(mixed_audio)
        self.global_audio_thread.start()

    def stop_all(self):
        self.is_playing_globally = False
        for track in self.tracks:
            if isinstance(track, MetronomeTrack):
                track.reset_beat_count()
            track.stop()
        if self.global_audio_thread and self.global_audio_thread.isRunning():
            sd.stop()
            self.global_audio_thread.wait()
        self.global_audio_thread = None
        audio_mixer.tracks.clear()  # Clear all tracks from the mixer
        sd.stop()  # Ensure all audio is stopped

    def closeEvent(self, event):
        self.stop_all()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())
