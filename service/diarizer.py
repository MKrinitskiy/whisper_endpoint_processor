from types import SimpleNamespace
import argparse
import logging
import os
import re

import torch
import torchaudio
from ctc_forced_aligner import (
    generate_emissions,
    get_alignments,
    get_spans,
    load_alignment_model,
    postprocess_results,
    preprocess_text,
)
from deepmultilingualpunctuation import PunctuationModel
from nemo.collections.asr.models.msdd_models import NeuralDiarizer

from helpers import (
    cleanup,
    create_config,
    get_realigned_ws_mapping_with_punctuation,
    get_sentences_speaker_mapping,
    get_speaker_aware_transcript,
    get_words_speaker_mapping,
    langs_to_iso,
    punct_model_langs,
    whisper_langs,
    write_srt,
)
from transcription_helpers import transcribe_batched

mtypes = {"cpu": "int8", "cuda": "float16"}


class Diarizer(object):
    def __init__(self, args: SimpleNamespace):
        self.args = args
        self.logger = logging.getLogger(__name__)
        pass

    def process_file(self, file_path, txt_fn, srt_fn):
        if self.args.stemming:
            # Isolate vocals from the rest of the audio

            return_code = os.system(
                f'python3 -m demucs.separate -n htdemucs --two-stems=vocals "{file_path}" -o "temp_outputs"'
            )

            if return_code != 0:
                self.logger.warning("Source splitting failed, using original audio file. Use --no-stem argument to disable it.")
                vocal_target = file_path
            else:
                vocal_target = os.path.join(
                    "temp_outputs",
                    "htdemucs",
                    os.path.splitext(os.path.basename(file_path))[0],
                    "vocals.wav",
                )
        else:
            vocal_target = file_path


        # Transcribe the audio file
        whisper_results, language, audio_waveform = transcribe_batched(vocal_target,
                                                                       self.args.language,
                                                                       self.args.batch_size,
                                                                       self.args.model_name,
                                                                       mtypes[self.args.device],
                                                                       self.args.suppress_numerals,
                                                                       self.args.device)

        # Forced Alignment
        alignment_model, alignment_tokenizer, alignment_dictionary = load_alignment_model(self.args.device,
                                                                                          dtype=torch.float16 if self.args.device == "cuda" else torch.float32)

        audio_waveform = (torch.from_numpy(audio_waveform).to(alignment_model.dtype).to(alignment_model.device))
        
        emissions, stride = generate_emissions(alignment_model, audio_waveform, batch_size=self.args.batch_size)

        del alignment_model
        torch.cuda.empty_cache()

        full_transcript = "".join(segment["text"] for segment in whisper_results)
        tokens_starred, text_starred = preprocess_text(full_transcript, romanize=True, language=langs_to_iso[language])
        segments, scores, blank_id = get_alignments(emissions, tokens_starred, alignment_dictionary)
        spans = get_spans(tokens_starred, segments, alignment_tokenizer.decode(blank_id))
        word_timestamps = postprocess_results(text_starred, spans, stride, scores)


        # convert audio to mono for NeMo combatibility
        ROOT = os.getcwd()
        temp_path = os.path.join(ROOT, "temp_outputs")
        os.makedirs(temp_path, exist_ok=True)
        torchaudio.save(os.path.join(temp_path, "mono_file.wav"),
                        audio_waveform.cpu().unsqueeze(0).float(),
                        16000,
                        channels_first=True)


        # Initialize NeMo MSDD diarization model
        msdd_model = NeuralDiarizer(cfg=create_config(temp_path)).to(self.args.device)
        msdd_model.diarize()

        del msdd_model
        torch.cuda.empty_cache()

        # Reading timestamps <> Speaker Labels mapping


        speaker_ts = []
        with open(os.path.join(temp_path, "pred_rttms", "mono_file.rttm"), "r") as f:
            lines = f.readlines()
            for line in lines:
                line_list = line.split(" ")
                s = int(float(line_list[5]) * 1000)
                e = s + int(float(line_list[8]) * 1000)
                speaker_ts.append([s, e, int(line_list[11].split("_")[-1])])

        wsm = get_words_speaker_mapping(word_timestamps, speaker_ts, "start")

        if language in punct_model_langs:
            # restoring punctuation in the transcript to help realign the sentences
            punct_model = PunctuationModel(model="kredor/punctuate-all")

            words_list = list(map(lambda x: x["word"], wsm))

            labled_words = punct_model.predict(words_list, chunk_size=230)

            ending_puncts = ".?!"
            model_puncts = ".,;:!?"

            # We don't want to punctuate U.S.A. with a period. Right?
            is_acronym = lambda x: re.fullmatch(r"\b(?:[a-zA-Z]\.){2,}", x)

            for word_dict, labeled_tuple in zip(wsm, labled_words):
                word = word_dict["word"]
                if (
                    word
                    and labeled_tuple[1] in ending_puncts
                    and (word[-1] not in model_puncts or is_acronym(word))
                ):
                    word += labeled_tuple[1]
                    if word.endswith(".."):
                        word = word.rstrip(".")
                    word_dict["word"] = word

        else:
            logging.warning(f"Punctuation restoration is not available for {language} language. Using the original punctuation.")

        wsm = get_realigned_ws_mapping_with_punctuation(wsm)
        ssm = get_sentences_speaker_mapping(wsm, speaker_ts)

        with open(txt_fn, "w", encoding="utf-8-sig") as f:
            get_speaker_aware_transcript(ssm, f)

        with open(srt_fn, "w", encoding="utf-8-sig") as srt:
            write_srt(ssm, srt)

        cleanup(temp_path)
