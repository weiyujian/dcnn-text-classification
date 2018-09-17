#d--c--n--n--分类算法

## Requirements

- Python 2.7
- Tensorflow > 0.12
- Numpy

## Training
CUDA_VISIBLE_DEVICES=0 python train.py --model_version=xxx

## Evaluating

```bash
CUDA_VISIBLE_DEVICES=0 python eval.py --checkpoint_dir=./runs/model_version/checkpoints/
```

## 说明
demo of d--c--n--n text classify, d-i-a-l-a-t-e & folding k max pooling

#语料格式
问句 \t 标签1 \t 标签2 ... \t 标签n



