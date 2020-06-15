"""
Author: Roman Feldbauer
Date: 2020-02-19
Description:
    Test client (cmd line interface)
"""
import argparse
from copy import deepcopy
import os
from pathlib import Path
import pytest
import shutil
import subprocess
import tempfile
from unittest import mock

import numpy as np
import pandas as pd
import torch

from deepnog.client import main
from deepnog.client.client import _start_prediction_or_training  # noqa
from deepnog import __version__

TEST_FILE = Path(__file__).parent.absolute() / "data/test_deepencoding.faa"
TRAINING_FASTA = Path(__file__).parent.absolute()/"data/test_training_dummy.faa"
TRAINING_CSV = Path(__file__).parent.absolute()/"data/test_training_dummy.faa.csv"
Y_TRUE = np.array([[0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2,
                    1, 1, 1, 1, 1, 1, 1, 1],
                   [0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2,
                    1, 1, 1, 1, 1, 1, 1, 1]])


def test_entrypoint():
    process = subprocess.run(['deepnog', '--version'], capture_output=True)
    assert process.returncode == 0, (f'Could not invoke deepnog on the '
                                     f'command line: '
                                     f'Return code {process.returncode}')
    assert f'deepnog {__version__}' in process.stdout.decode('ascii'),\
        f'Incorrect version output: {process.stdout}'


@pytest.mark.parametrize('tax', [1, 2, ])
def test_inference_cmd_line_invocation(tax):
    # Using out file
    outfile = f'out{tax}.csv'
    proc = subprocess.run(['deepnog', 'infer',
                           f'{TEST_FILE}',
                           '--tax', f'{tax}',
                           '--out', f'{outfile}',
                           '--verbose', f'{0}',
                           ],
                          capture_output=True,
                          )
    outfile = Path(outfile)
    assert outfile.is_file(), (f'Stdout of call:\n{proc.stdout}\n\n'
                               f'Stderr of call:\n{proc.stderr}')
    outfile.unlink()

    # Using output to stdout
    proc = subprocess.run(['deepnog', 'infer',
                           f'{TEST_FILE}',
                           '--tax', f'{tax}',
                           '--verbose', '3',
                           ],
                          capture_output=True,
                          )
    for log_str in [b'INFO', b'WARNING', b'DEBUG', b'ERROR', b'CRITICAL']:
        assert log_str not in proc.stdout, 'stdout polluted by logging messages,' \
                                           'when it should only contain predictions.'
    for log_str in [b'INFO', b'DEBUG']:
        assert log_str in proc.stderr, 'missing log messages in stderr'
    # Check the prediction in stdout (omitting volatile confidence values)
    linesep = os.linesep.encode()
    correct_out = b'sequence_id,prediction,confidence' + linesep + b'0,COG0443'
    assert correct_out in proc.stdout, f'Incorrect prediction output in stderr: {proc.stderr}'


@mock.patch('argparse.ArgumentParser.parse_args',
            return_value=argparse.Namespace(phase='infer',
                                            tax='2',
                                            out='out.mock.2',
                                            file=TEST_FILE,
                                            fformat='fasta',
                                            outformat='csv',
                                            database='eggNOG5',
                                            verbose=0,
                                            device='auto',
                                            num_workers=0,
                                            confidence_threshold=None,
                                            architecture='deepencoding',
                                            weights=None,
                                            batch_size=1,
                                            # train only
                                            training_sequences=None,
                                            validation_sequences=None,
                                            labels=None,
                                            n_epochs=None,
                                            shuffle=None,
                                            learning_rate=None,
                                            ))
def test_main_and_argparsing(mock_args):  # noqa
    main()
    Path('out.mock.2').unlink()


def test_args_sanity_check():
    _, existing_file = tempfile.mkstemp()
    args = argparse.Namespace(
        phase='infer', tax='2', out='out.mock.2', file=TEST_FILE, fformat='fasta', outformat='csv',
        database='eggNOG5', verbose=0, device='auto', num_workers=0, confidence_threshold=0.5,
        architecture='deepencoding', weights=None, batch_size=1,
        # train only
        training_sequences=None, validation_sequences=None, labels=None, n_epochs=None,
        shuffle=None, learning_rate=None,
    )
    args_bs = deepcopy(args)
    args_bs.batch_size = 0
    with pytest.raises(ValueError):
        _start_prediction_or_training(args_bs)
    args_out = deepcopy(args)
    args_out.out = existing_file
    with pytest.raises(FileExistsError):
        _start_prediction_or_training(args_out)
    args_device = deepcopy(args)
    args_device.device = None
    with pytest.raises(ValueError):
        _start_prediction_or_training(args_device)
    args_train = deepcopy(args)
    args_train.phase = 'train'
    args_train.n_epochs = 0
    with pytest.raises(ValueError):
        _start_prediction_or_training(args_train)
    Path(existing_file).unlink()
    args_confidence = deepcopy(args)
    args_confidence.confidence_threshold = 0
    with pytest.raises(ValueError):
        _start_prediction_or_training(args_confidence)
    args_confidence.confidence_threshold = 1.000001
    with pytest.raises(ValueError):
        _start_prediction_or_training(args_confidence)


def test_training_cmd_line_invocation():
    outdir = tempfile.mkdtemp(prefix='deepnog_test_')
    tax = 2
    proc = subprocess.run(['deepnog', 'train',
                           f'{TRAINING_FASTA}', f'{TRAINING_FASTA}', f'{TRAINING_CSV}',
                           '--tax', f'{tax}', '--out', outdir, '--database', 'dummy_db',
                           '--n_epochs', f'{2}', '--verbose', '0',
                           ],
                          capture_output=True,
                          )
    outdir = Path(outdir)
    assert outdir.is_dir(), (f'Stdout of call:\n{proc.stdout}\n\n'
                             f'Stderr of call:\n{proc.stderr}')
    assert len(list(outdir.iterdir())) == 3, 'Training files missing'
    for f in outdir.iterdir():
        if str(f).endswith('csv'):
            df = pd.read_csv(f)
            for k in ['phase', 'epoch', 'accuracy', 'loss']:
                assert k in df.columns, f'Column {k} missing in output csv file'
            np.testing.assert_almost_equal(df.accuracy.iloc[-1], 1.0, decimal=3)
            np.testing.assert_almost_equal(df.loss.iloc[-1], 0.0, decimal=3)
            assert df.phase.iloc[-2] == 'train', 'Second last phase was not "train".'
            assert df.phase.iloc[-1] == 'val', 'Last phase was not "val".'
            np.testing.assert_equal(df.epoch, np.array([0, 0, 1, 1])),\
                'Wrong number of epochs in csv file'
            f.unlink()
        elif str(f).endswith('npz'):
            c = np.load(str(f))
            # Here we use the same data for training and validation
            np.testing.assert_equal(c['y_train_true'], Y_TRUE)
            np.testing.assert_equal(c['y_val_true'], Y_TRUE)
            np.testing.assert_equal(c['y_val_pred'], Y_TRUE)
            # Predictions during training epoch 0 may be anything
            np.testing.assert_equal(c['y_train_pred'][1], Y_TRUE[1])
            f.unlink()
        elif str(f).endswith('pt') or str(f).endswith('pth'):
            model = torch.load(str(f))
            for k in ['classes', 'model_state_dict', ]:
                assert k in model
            np.testing.assert_equal(model['classes'], np.array(['28H52', '99A99', 'ZYX12']))
            assert model['model_state_dict']['classification1.weight'].shape == (3, 1200)
            f.unlink()
        else:
            assert False, f'Unexpected file in output dir: {f}'

    try:
        shutil.rmtree(outdir)
    except OSError:
        pass
