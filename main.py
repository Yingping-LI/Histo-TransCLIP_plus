import os
import time
import random
import argparse
#import open_clip
import numpy as np
from datasets import get_all_dataloaders
from utils import *

from plip.plip import PLIP
from open_clip.src.open_clip.factory import add_model_config,create_model_and_transforms
from open_clip.src.open_clip.factory import create_model_from_pretrained as open_clip_create_model_from_pretrained
from CONCH.conch.open_clip_custom import create_model_from_pretrained
from transformers import AutoProcessor, AutoModelForZeroShotImageClassification


def get_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', default='dtd', help='dataset name', type=str)
    parser.add_argument('--root_path', default='./datasets', type=str)
    parser.add_argument('--method', default='TransCLIP', type=str,
                        help='')
    parser.add_argument('--model', default='Quilt', type=str,
                        help='')
    parser.add_argument('--shots', default=0, type=int)
    parser.add_argument('--seed', default=1, type=int)
    parser.add_argument('--backbone', default='vit_b16', type=str)

    parser.add_argument('--prototypes_path', default="./prototypes")
    parser.add_argument('--setting', default="")
    parser.add_argument('--prototypes_method', default="")
    parser.add_argument('--prototypes_dataset', default="")
    parser.add_argument('--prototypes_shots', default=16)

    args = parser.parse_args()

    return args


def set_random_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def main():
    backbones = {'rn50': 'RN50',
                 'rn101': 'RN101',
                 'vit_b16': 'ViT-B/16',
                 'vit_b32': 'ViT-B/32',
                 'vit_l14': 'ViT-L/14'}

    # Load config file
    args = get_arguments()

    cfg = {'dataset': args.dataset}

    cache_dir = os.path.join('./caches', cfg['dataset'])
    os.makedirs(cache_dir, exist_ok=True)
    cfg['cache_dir'] = cache_dir
    cfg['load_cache'] = True
    cfg['load_pre_feat'] = False

    print("\nRunning configs.")

    cfg['backbone'] = backbones[args.backbone]

    cfg['seed'] = args.seed
    cfg['root_path'] = args.root_path
    cfg['method'] = args.method
    cfg['model'] = args.model
    cfg['shots'] = args.shots

    cfg['prototypes_path'] = args.prototypes_path
    cfg['setting'] = args.setting
    cfg['prototypes_method'] = args.prototypes_method
    cfg['prototypes_dataset'] = args.prototypes_dataset
    cfg['prototypes_shots'] = args.prototypes_shots

    print(cfg, "\n")

    # CLIP
    _, preprocess_val = clip.load(cfg['backbone'])
    if args.model == 'CLIP':
        clip_model, preprocess_val = clip.load(cfg['backbone'])
    if args.model == 'Quilt':
        #clip_model, preprocess_train, preprocess_val = create_model_and_transforms('hf-hub:wisdomik/QuiltNet-B-16') #Original code

        # '''
        # QuiltNet-B-16
        # '''
        # add_model_config('Quilt-1m/wisdomik/QuiltNet-B-16/QuiltNet-B-16.json')
        # clip_model, preprocess_val = open_clip_create_model_from_pretrained('QuiltNet-B-16', pretrained='Quilt-1m/wisdomik/QuiltNet-B-16/open_clip_pytorch_model.bin')

        # '''
        # QuiltNet-B-16-PMB
        # '''
        # add_model_config('Quilt-1m/wisdomik/QuiltNet-B-16-PMB/QuiltNet-B-16-PMB.json')
        # clip_model, preprocess_val = open_clip_create_model_from_pretrained('QuiltNet-B-16-PMB',
        #                                                                     pretrained='Quilt-1m/wisdomik/QuiltNet-B-16-PMB/open_clip_pytorch_model.bin')

        '''
        QuiltNet-B-32
        '''
        add_model_config('Quilt-1m/wisdomik/QuiltNet-B-32/QuiltNet-B-32.json')
        clip_model, preprocess_val = open_clip_create_model_from_pretrained('QuiltNet-B-32',
                                                                            pretrained='Quilt-1m/wisdomik/QuiltNet-B-32/open_clip_pytorch_model.bin')
    elif args.model == 'CONCH':
        clip_model, preprocess_val = create_model_from_pretrained("conch_ViT-B-16", checkpoint_path="CONCH/checkpoints/conch/pytorch_model.bin")
    elif args.model == "PLIP":
        #clip_model, preprocess  = PLIP('vinid/plip')
        #processor = AutoProcessor.from_pretrained("vinid/plip")
        clip_model = AutoModelForZeroShotImageClassification.from_pretrained("plip/vinid/plip")
    clip_model.cuda().eval()

    # Prepare dataset
    set_random_seed(args.seed)

    print("Preparing dataset.")

    train_loader, val_loader, test_loader, dataset = get_all_dataloaders(cfg, preprocess_val)

    print("Loading features.")
    print(clip_model)
    feature_time = time.time()
    shot_features, shot_labels, val_features, val_labels, test_features, test_labels, clip_prototypes = get_all_features(
        cfg, train_loader, val_loader, test_loader, dataset, clip_model)
    print("feature time {}".format(str(time.time()-feature_time)))
    clip_model = clip_model.to('cpu')  # unload CLIP model from VRAM

    if args.method == 'TransCLIP':
        transclip_time = time.time()
        from TransCLIP_solver.TransCLIP import TransCLIP_solver
        if cfg['shots'] == 0:
            TransCLIP_solver(shot_features, shot_labels, val_features, val_labels, test_features, test_labels,
                             clip_prototypes)
        else:
            shot_features = shot_features.unsqueeze(0)
            TransCLIP_solver(shot_features, shot_labels, val_features, val_labels, test_features, test_labels,
                             clip_prototypes)
        print("feature time {}".format(str(time.time()-transclip_time)))

    elif args.method == 'On-top':

        from TransCLIP_solver.TransCLIP import TransCLIP_solver
        from TransCLIP_solver.bench_utils import prepare_for_bench

        test_features, test_labels, initial_prototypes, initial_logits, clip_prototypes = prepare_for_bench(args,
                                                                                                            test_features,
                                                                                                            test_labels,
                                                                                                            clip_prototypes)

        if cfg['shots'] == 0:
            TransCLIP_solver(shot_features, shot_labels, val_features, val_labels, test_features, test_labels,
                             clip_prototypes, initial_prototypes, initial_logits)
        else:
            shot_features = shot_features.unsqueeze(0)
            TransCLIP_solver(shot_features, shot_labels, val_features, val_labels, test_features, test_labels,
                             clip_prototypes, initial_prototypes, initial_logits)


    elif args.method == 'transductive_finetuning':
        device = clip_prototypes.device
        shot_features = shot_features.type(torch.FloatTensor).squeeze().to(device)
        val_features = val_features.type(torch.FloatTensor).squeeze().to(device)
        test_features = test_features.type(torch.FloatTensor).squeeze().to(device)
        clip_prototypes = clip_prototypes.type(torch.FloatTensor).squeeze().to(device)
        from baselines.runner import run_transductive_finetuning
        run_transductive_finetuning(cfg, shot_features, shot_labels, val_features, val_labels, test_features,
                                    test_labels,
                                    clip_prototypes)
    elif args.method == 'bdcspn':
        device = clip_prototypes.device
        shot_features = shot_features.type(torch.FloatTensor).squeeze().to(device)
        val_features = val_features.type(torch.FloatTensor).squeeze().to(device)
        test_features = test_features.type(torch.FloatTensor).squeeze().to(device)
        clip_prototypes = clip_prototypes.type(torch.FloatTensor).squeeze().to(device)
        from baselines.runner import run_bdcspn
        run_bdcspn(cfg, shot_features, shot_labels, val_features, val_labels, test_features, test_labels,
                   clip_prototypes)
    elif args.method == 'laplacian_shot':
        device = clip_prototypes.device
        shot_features = shot_features.type(torch.FloatTensor).squeeze().to(device)
        val_features = val_features.type(torch.FloatTensor).squeeze().to(device)
        test_features = test_features.type(torch.FloatTensor).squeeze().to(device)
        clip_prototypes = clip_prototypes.type(torch.FloatTensor).squeeze().to(device)
        from baselines.runner import run_laplacian_shot
        run_laplacian_shot(cfg, shot_features, shot_labels, val_features, val_labels, test_features, test_labels,
                           clip_prototypes)
    elif args.method == 'ptmap':
        device = clip_prototypes.device
        shot_features = shot_features.type(torch.FloatTensor).squeeze().to(device)
        val_features = val_features.type(torch.FloatTensor).squeeze().to(device)
        test_features = test_features.type(torch.FloatTensor).squeeze().to(device)
        clip_prototypes = clip_prototypes.type(torch.FloatTensor).squeeze().to(device)
        from baselines.runner import run_pt_map
        run_pt_map(cfg, shot_features, shot_labels, val_features, val_labels, test_features, test_labels,
                   clip_prototypes)
    elif args.method == 'tim':
        device = clip_prototypes.device
        shot_features = shot_features.type(torch.FloatTensor).squeeze().to(device)
        val_features = val_features.type(torch.FloatTensor).squeeze().to(device)
        test_features = test_features.type(torch.FloatTensor).squeeze().to(device)
        clip_prototypes = clip_prototypes.type(torch.FloatTensor).squeeze().to(device)
        from baselines.runner import run_tim
        run_tim(cfg, shot_features, shot_labels, val_features, val_labels, test_features, test_labels,
                clip_prototypes, version='adm')


if __name__ == '__main__':
    main()
