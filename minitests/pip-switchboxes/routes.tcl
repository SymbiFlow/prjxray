# Copyright (C) 2017-2020  The Project X-Ray Authors
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC

set_property FIXED_ROUTE {} [get_nets]
route_design -unroute

route_via x_OBUF {INT_L_X10Y118/NR1BEG1 INT_L_X10Y119/EE2BEG0 INT_L_X12Y119/EE2BEG0 INT_R_X13Y118/SW2END0 INT_R_X13Y118/WW4BEG1}
route_via y_OBUF {INT_L_X10Y116/NR1BEG1 INT_L_X10Y117/EE2BEG0 INT_L_X12Y117/EE2BEG0 INT_R_X13Y116/SW2END0 INT_R_X13Y116/WW4BEG1}
route_via z_OBUF {INT_L_X10Y114/NR1BEG1 INT_L_X10Y115/EE2BEG0 INT_L_X12Y115/EE2BEG0 INT_R_X13Y114/SW2END0 INT_R_X13Y114/WW4BEG1}

route_design

write_checkpoint -force routes.dcp
write_bitstream -force routes.bit
