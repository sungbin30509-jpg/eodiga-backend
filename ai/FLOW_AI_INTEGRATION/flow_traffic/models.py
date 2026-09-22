"""Shared LightGBM interface; grouped candidates always cover the same cohort."""

from pathlib import Path
import json

import numpy as np
import pandas as pd

from .lead_sampling import bin_ids
from .io import dump


# ============================================================
# LightGBM 모델 로더
#
# Windows 한글 경로 문제 대응
#
# 기존:
# lgb.Booster(model_file="한글경로/.../global.txt")
#
# 문제:
# LightGBM native library가 Windows에서
# 한글/비ASCII 경로를 정상적으로 열지 못할 수 있음.
#
# 해결:
# Python이 모델 txt를 먼저 읽고
# model_str로 LightGBM에 전달.
#
# 모델 자체는 수정하지 않으며
# 재학습도 수행하지 않음.
# ============================================================

def load_booster_from_path(
    model_path,
):

    import lightgbm as lgb

    model_path = Path(
        model_path
    )

    model_text = model_path.read_text(
        encoding="utf-8"
    )

    return lgb.Booster(
        model_str=model_text
    )


# ============================================================
# Feature Matrix
# ============================================================

def matrix(
    d,
    features,
    categories,
):

    x = d[
        features
    ].copy()

    x["link_id"] = pd.Categorical(
        x.link_id.where(
            x.link_id.isin(
                categories
            )
        ),
        categories=categories,
    )

    for f in features:

        if f != "link_id":

            x[f] = (
                pd.to_numeric(
                    x[f],
                    errors="raise",
                )
                .astype(
                    "float32"
                )
            )

    return x


# ============================================================
# Partition ID
# ============================================================

def partition_ids(
    d,
    structure,
    c,
):

    if structure == "single":

        return np.zeros(
            len(d),
            dtype=int,
        )

    if structure == "lead_bins":

        return bin_ids(
            d.lead_minutes,
            c["model"][
                "lead_bins"
            ],
        )

    return bin_ids(
        (
            d.target_time.dt.hour
            * 60
            +
            d.target_time.dt.minute
        ),
        c["model"][
            "target_time_bins"
        ],
    )


# ============================================================
# Model Training
#
# 기존 팀원 코드 그대로 유지
# 이번 통합에서는 호출하지 않음.
# ============================================================

def fit_candidate(
    train,
    val,
    features,
    c,
    structure,
    folder,
    locked=None,
):

    import lightgbm as lgb

    folder = Path(
        folder
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    categories = sorted(
        train.link_id
        .unique()
        .tolist()
    )

    x = matrix(
        train,
        features,
        categories,
    )

    ids = partition_ids(
        train,
        structure,
        c,
    )

    vids = (
        partition_ids(
            val,
            structure,
            c,
        )
        if val is not None
        else None
    )

    models = {}

    skipped = []

    # Global fallback avoids dropping sparse
    # partitions from validation comparison.
    keys = [
        "global"
    ] + (
        []
        if structure == "single"
        else [
            str(i)
            for i
            in sorted(
                set(ids)
            )
        ]
    )

    for key in keys:

        tm = (
            np.ones(
                len(train),
                bool,
            )
            if key == "global"
            else ids == int(key)
        )

        vm = (
            None
            if val is None
            else (
                np.ones(
                    len(val),
                    bool,
                )
                if key == "global"
                else vids == int(key)
            )
        )

        if (
            key != "global"
            and (
                tm.sum()
                <
                c["model"][
                    "min_partition_rows"
                ]
                or (
                    vm is not None
                    and vm.sum() < 2
                )
            )
        ):

            skipped.append({

                "partition":
                    key,

                "reason":
                    (
                        "insufficient train/"
                        "validation rows; "
                        "global fallback"
                    ),

                "train_rows":
                    int(
                        tm.sum()
                    ),
            })

            continue

        if (
            locked is not None
            and key
            not in locked[
                "models"
            ]
        ):

            continue

        params = dict(
            c["model"][
                "lightgbm"
            ]
        )

        if locked is not None:

            params[
                "n_estimators"
            ] = (
                locked[
                    "models"
                ][
                    key
                ][
                    "iterations"
                ]
            )

        model = lgb.LGBMRegressor(
            **params,
            n_jobs=c["run"][
                "threads"
            ],
            random_state=c[
                "run"
            ][
                "seed"
            ],
            deterministic=True,
            force_col_wise=True,
        )

        extra = {}

        if val is not None:

            extra = {

                "eval_X":
                    matrix(
                        val.loc[vm],
                        features,
                        categories,
                    ),

                "eval_y":
                    val.loc[
                        vm,
                        "y_speed_kmh",
                    ],

                "eval_metric":
                    "l1",

                "callbacks": [
                    lgb.early_stopping(
                        c["model"][
                            "early_stopping_rounds"
                        ],
                        verbose=False,
                    )
                ],
            }

        model.fit(
            x.loc[tm],
            train.loc[
                tm,
                "y_speed_kmh",
            ],
            sample_weight=train.loc[
                tm,
                "sample_weight",
            ],
            categorical_feature=[
                "link_id"
            ],
            **extra,
        )

        filename = (
            f"{key}.txt"
        )

        model.booster_.save_model(
            str(
                folder
                /
                filename
            )
        )

        models[
            key
        ] = {

            "file":
                filename,

            "iterations":
                int(
                    model.best_iteration_
                    or params[
                        "n_estimators"
                    ]
                ),

            "train_rows":
                int(
                    tm.sum()
                ),
        }

    meta = {

        "structure":
            structure,

        "models":
            models,

        "skipped_partitions":
            skipped,

        "features":
            features,

        "categories":
            categories,
    }

    dump(
        folder
        /
        "model_index.json",
        meta,
    )

    return meta


# ============================================================
# Prediction
#
# 이 부분만 핵심적으로 변경됨.
#
# LightGBM이 직접 Windows 한글 경로를
# 열지 않고 Python이 모델 파일을 읽은 후
# model_str로 전달.
# ============================================================

def predict_candidate(
    d,
    folder,
    c,
):

    folder = Path(
        folder
    )

    meta = json.loads(
        (
            folder
            /
            "model_index.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    x = matrix(
        d,
        meta[
            "features"
        ],
        meta[
            "categories"
        ],
    )

    ids = partition_ids(
        d,
        meta[
            "structure"
        ],
        c,
    )


    # ========================================================
    # Global Model
    # ========================================================

    global_model_path = (
        folder
        /
        meta[
            "models"
        ][
            "global"
        ][
            "file"
        ]
    )

    global_model = (
        load_booster_from_path(
            global_model_path
        )
    )


    pred = global_model.predict(
        x,
        num_threads=c[
            "run"
        ][
            "threads"
        ],
    )


    # ========================================================
    # Partition Models
    # ========================================================

    for (
        key,
        spec,
    ) in meta[
        "models"
    ].items():

        if key == "global":

            continue


        mask = (
            ids
            ==
            int(key)
        )


        if mask.any():

            model_path = (
                folder
                /
                spec[
                    "file"
                ]
            )


            model = (
                load_booster_from_path(
                    model_path
                )
            )


            pred[
                mask
            ] = model.predict(

                x.loc[
                    mask
                ],

                num_threads=c[
                    "run"
                ][
                    "threads"
                ],
            )


    return np.asarray(
        pred
    )