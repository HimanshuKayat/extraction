from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)


class ModelClient(Protocol):

    def generate(
        self,
        messages: list[dict[str, str]],
        mode: str = "tool_selection",
    ) -> str:
        ...


@dataclass
class GenerationConfig:

    enable_thinking: bool = False
    max_new_tokens: int = 256
    temperature: float = 0.0
    do_sample: bool = False


class QwenModel:

    DEFAULT_MODEL = "Qwen/Qwen3-8B"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        load_in_4bit: bool = True,
        device_map: str | dict = "auto",
    ):

        self.model_name = model_name

        self._tokenizer = (
            AutoTokenizer.from_pretrained(
                model_name,
                trust_remote_code=True,
            )
        )

        quantization_config = None

        if load_in_4bit:

            quantization_config = (
                BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=(
                        torch.float16
                    ),
                    bnb_4bit_use_double_quant=True,
                )
            )

        self._model = (
            AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=(
                    quantization_config
                ),
                device_map=device_map,
                dtype=torch.float16,
                trust_remote_code=True,
            )
        )

        self._model.eval()

        self.generation_configs = {

            "tool_selection": GenerationConfig(
                enable_thinking=False,
                max_new_tokens=256,
                temperature=0.0,
                do_sample=False,
            ),

            "reasoning": GenerationConfig(
                enable_thinking=True,
                max_new_tokens=1024,
                temperature=0.6,
                do_sample=True,
            ),
        }

    def generate(
        self,
        messages: list[dict[str, str]],
        mode: str = "tool_selection",
    ) -> str:

        if mode not in self.generation_configs:
            raise ValueError(
                f"Unknown generation mode: {mode}"
            )

        config = self.generation_configs[mode]

        prompt = (
            self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=(
                    config.enable_thinking
                ),
            )
        )

        inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
        )

        device = self._model.device

        inputs = {
            key: value.to(device)
            for key, value in inputs.items()
        }

        generation_kwargs = {
            "max_new_tokens": (
                config.max_new_tokens
            ),
            "do_sample": config.do_sample,
            "pad_token_id": (
                self._tokenizer.eos_token_id
            ),
        }

        if config.do_sample:

            generation_kwargs[
                "temperature"
            ] = config.temperature

        with torch.inference_mode():

            outputs = self._model.generate(
                **inputs,
                **generation_kwargs,
            )

        input_length = (
            inputs["input_ids"]
            .shape[-1]
        )

        generated = outputs[
            0,
            input_length:,
        ]

        return self._tokenizer.decode(
            generated,
            skip_special_tokens=True,
        ).strip()