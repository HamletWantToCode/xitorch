import warnings
import torch
from torch.autograd import gradcheck, gradgradcheck
from xitorch.interpolate.interp1 import Interp1D
from xitorch._tests.utils import device_dtype_float_test

@device_dtype_float_test(only64=True)
def test_interp1_cspline(dtype, device):
    dtype_device_kwargs = {"dtype": dtype, "device": device}
    bc_type = "clamped"
    x = torch.tensor([0.0, 0.2, 0.3, 0.5, 0.8, 1.0], **dtype_device_kwargs).requires_grad_()
    y1 = torch.tensor([1.0, 1.5, 2.1, 1.1, 2.3, 2.5], **dtype_device_kwargs).requires_grad_()
    y2 = torch.tensor([[1.0, 1.5, 2.1, 1.1, 2.3, 2.5],
                       [0.8, 1.2, 2.2, 0.4, 3.2, 1.2]], **dtype_device_kwargs).requires_grad_()
    xq1 = torch.linspace(0, 1, 10, **dtype_device_kwargs).requires_grad_()
    xq2 = torch.linspace(0, 1, 4, **dtype_device_kwargs).requires_grad_()

    # true results (obtained from scipy.interpolate.CubicSpline)
    # from scipy.interpolate import CubicSpline
    # print("yq11:", CubicSpline(x.detach(), y1.detach(), bc_type=bc_type)(xq1.detach()))
    # print("yq12:", CubicSpline(x.detach(), y1.detach(), bc_type=bc_type)(xq2.detach()))
    # print("yq21:", CubicSpline(x.detach(), y2[1].detach(), bc_type=bc_type)(xq1.detach()))
    # print("yq22:", CubicSpline(x.detach(), y2[1].detach(), bc_type=bc_type)(xq2.detach()))

    yq11_true = torch.tensor([1.        , 1.10966822, 1.65764362, 2.08516021, 1.40964624, 1.04718761,
                              1.52146065, 2.19990128, 2.49291361, 2.5       ],
                              **dtype_device_kwargs)
    yq12_true = torch.tensor([1.        , 2.08516021, 1.52146065, 2.5       ], **dtype_device_kwargs)
    yq21_true = torch.tensor([[1.        , 1.10966822, 1.65764362, 2.08516021, 1.40964624, 1.04718761,
                               1.52146065, 2.19990128, 2.49291361, 2.5       ],
                              [0.8       , 0.75490137, 1.45269956, 2.13861483, 0.8463294,  0.57694735,
                               2.06124231, 3.20656708, 2.2875088,  1.2       ]],
                               **dtype_device_kwargs)
    yq22_true = torch.tensor([[1.        , 2.08516021, 1.52146065, 2.5       ],
                              [0.8       , 2.13861483, 2.06124231, 1.2       ]],
                              **dtype_device_kwargs)

    def interp(x, y, xq):
        return Interp1D(x, y, method="cspline", bc_type=bc_type, extrap="mirror")(xq)

    yq11 = interp(x, y1, xq1)
    yq12 = interp(x, y1, xq2)
    yq21 = interp(x, y2, xq1)
    yq22 = interp(x, y2, xq2)
    # import matplotlib.pyplot as plt
    # from scipy.interpolate import CubicSpline
    # xx = torch.linspace(0, 1, 1000, **dtype_device_kwargs)
    # xx2 = torch.linspace(-1, 2, 1000, **dtype_device_kwargs)
    # plt.plot(xx2, interp(x, y1, xx2).detach().numpy())
    # plt.plot(xx, CubicSpline(x.detach(), y1.detach(), bc_type="clamped")(xx.detach()))
    # plt.plot(x.detach(), y1.detach(), 'x')
    # plt.show()
    assert torch.allclose(yq11, yq11_true)
    assert torch.allclose(yq12, yq12_true)
    assert torch.allclose(yq21, yq21_true)
    assert torch.allclose(yq22, yq22_true)

    gradcheck(interp, (x, y1, xq1))
    gradcheck(interp, (x, y1, xq2))
    gradcheck(interp, (x, y2, xq1))
    gradcheck(interp, (x, y2, xq2))

    gradgradcheck(interp, (x, y1, xq1))
    gradgradcheck(interp, (x, y1, xq2))
    gradgradcheck(interp, (x, y2, xq1))
    gradgradcheck(interp, (x, y2, xq2))

@device_dtype_float_test(only64=True)
def test_interp1_editable_module(dtype, device):
    dtype_device_kwargs = {"dtype": dtype, "device": device}
    x = torch.tensor([0.0, 0.2, 0.3, 0.5, 0.8, 1.0], **dtype_device_kwargs).requires_grad_()
    y = torch.tensor([[1.0, 1.5, 2.1, 1.1, 2.3, 2.5],
                      [0.8, 1.2, 2.2, 0.4, 3.2, 1.2]], **dtype_device_kwargs).requires_grad_()
    xq = torch.linspace(0, 1, 10, **dtype_device_kwargs).requires_grad_()

    methods = ["cspline"]
    for method in methods:
        cls1 = Interp1D(x, y, method=method)
        cls2 = Interp1D(x, method=method)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            cls1.assertparams(cls1.__call__, xq)
            cls2.assertparams(cls2.__call__, xq, y)

@device_dtype_float_test(only64=True)
def test_extrap(dtype, device):
    dtype_device_kwargs = {"dtype": dtype, "device": device}
    x = torch.tensor([0.0, 0.2, 0.3, 0.5, 0.8, 1.0], **dtype_device_kwargs).requires_grad_()
    y1 = torch.tensor([[1.0, 2.1, 1.5, 1.1, 2.3, 2.5],
                       [0.0, 1.2, 2.2, 0.4, 3.2, 1.2]], **dtype_device_kwargs).requires_grad_()
    xq1 = torch.tensor([0.0, 1./3, 2./3, 3./3, -1./3, -1.0, -4./3, 4./3, 6./3, 7./3, 9./3], **dtype_device_kwargs).requires_grad_()

    # true results (obtained from scipy.interpolate.CubicSpline)
    nan = float("nan")
    yq_nan_true = torch.tensor([
        [1., 1.3127193 , 1.7445744 , 2.5, nan, nan, nan, nan, nan, nan, nan],
        [0., 2.13368966, 1.82654566, 1.2, nan, nan, nan, nan, nan, nan, nan],
    ], **dtype_device_kwargs)
    yq_mir_true = torch.tensor([
        [1., 1.3127193 , 1.7445744 , 2.5, 1.3127193 , 2.5, 1.7445744 , 1.7445744 , 1., 1.3127193 , 2.5],
        [0., 2.13368966, 1.82654566, 1.2, 2.13368966, 1.2, 1.82654566, 1.82654566, 0., 2.13368966, 1.2],
    ], **dtype_device_kwargs)
    yq_bnd_true = torch.tensor([
        [1., 1.3127193 , 1.7445744 , 2.5, 1., 1., 1., 2.5, 2.5, 2.5, 2.5],
        [0., 2.13368966, 1.82654566, 1.2, 0., 0., 0., 1.2, 1.2, 1.2, 1.2],
    ], **dtype_device_kwargs)
    yq_1_true = torch.tensor([
        [1., 1.3127193 , 1.7445744 , 2.5, 1., 1., 1., 1., 1., 1., 1.],
        [0., 2.13368966, 1.82654566, 1.2, 1., 1., 1., 1., 1., 1., 1.],
    ], **dtype_device_kwargs)
    cal = lambda x: x * 2.
    yq_cal_true = torch.tensor([
        [1., 1.3127193 , 1.7445744 , 2.5, -2./3, -2., -8./3, 8./3, 12./3, 14./3, 18./3],
        [0., 2.13368966, 1.82654566, 1.2, -2./3, -2., -8./3, 8./3, 12./3, 14./3, 18./3],
    ], **dtype_device_kwargs)
    extraps = ["nan", "mirror", "bound", 1.0, cal]
    yq_trues = [yq_nan_true, yq_mir_true, yq_bnd_true, yq_1_true, yq_cal_true]

    def interp(x, y, xq, extrap):
        return Interp1D(x, y, extrap=extrap, method="cspline", bc_type="natural")(xq)

    for extrap, yq_true in zip(extraps, yq_trues):
        print("Extrap: %s" % extrap)
        yq = interp(x, y1, xq1, extrap=extrap)
        assert torch.allclose(yq, yq_true, equal_nan=True)

if __name__ == "__main__":
    test_interp1_cspline()
