#!/usr/bin/env python3


import math
from typing import Any, List

from uncertainties import UFloat, ufloat

import ROOT


# see https://root-forum.cern.ch/t/tf1-eval-as-a-function-in-rdataframe/50699/3
def declareInCpp(**kwargs: Any) -> None:
  '''Creates C++ variables (names given by keys) for PyROOT objects (given values) in PyVars:: namespace'''
  for key, value in kwargs.items():
    ROOT.gInterpreter.Declare(  # type: ignore
f'''
namespace PyVars
{{
  auto& {key} = *reinterpret_cast<{type(value).__cpp_name__}*>({ROOT.addressof(value)});
}}
''')


if __name__ == "__main__":
  ROOT.gROOT.SetBatch(True)  # type: ignore
  ROOT.EnableImplicitMT()    # type: ignore

  # linear combination of legendre polynomials up to given degree
  maxDegree = 5
  terms = tuple(f"[{degree}] * ROOT::Math::legendre({degree}, x)" for degree in range(maxDegree + 1))
  legendrePolLC = ROOT.TF1("legendrePolLC", " + ".join(terms), -1, +1)  # type: ignore
  legendrePolLC.SetNpx(1000)  # used in numeric integration performed by GetRandom()
  legendrePolLC.SetParameters(0.5, 0.5, 0.25, -0.25, -0.125, 0.125)
  legendrePolLC.SetMinimum(0)

  canv = ROOT.TCanvas()  # type: ignore
  legendrePolLC.Draw()
  canv.SaveAs(f"{legendrePolLC.GetName()}.pdf")

  # generate data according to linear combination of legendre polynomials
  ROOT.gRandom.SetSeed(1234567890)  # type: ignore
  declareInCpp(legendrePolLC = legendrePolLC)
  nmbEvents = 100000
  df = ROOT.RDataFrame(nmbEvents)  # type: ignore
  dfData = df.Define("val", "PyVars::legendrePolLC.GetRandom()")
  # dfData.Snapshot("data", f"{legendrePolLC.GetName()}.root")

  # plot data
  hist = dfData.Histo1D(ROOT.RDF.TH1DModel(f"{legendrePolLC.GetName()}_hist", "", 100, -1, +1), "val")  # type: ignore
  hist.SetMinimum(0)
  hist.Draw()
  canv.SaveAs(f"{hist.GetName()}.pdf")

  # calculate unnormalized moments
  moments: List[UFloat] = []
  for degree in range(maxDegree + 5):
    dfMoment = dfData.Define("legendrePol", f"ROOT::Math::legendre({degree}, val)")
    momentVal = dfMoment.Sum("legendrePol").GetValue()
    momentErr = math.sqrt(nmbEvents) * dfMoment.StdDev("legendrePol").GetValue()  # iid events: Var[sum_i^N f(x_i)] = sum_i^N Var[f] = N * Var[f]
    moments.append(ufloat(momentVal, momentErr))
  print(moments)
