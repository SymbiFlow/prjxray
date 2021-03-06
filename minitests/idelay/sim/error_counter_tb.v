// Copyright (C) 2017-2020  The Project X-Ray Authors.
//
// Use of this source code is governed by a ISC-style
// license that can be found in the LICENSE file or at
// https://opensource.org/licenses/ISC
//
// SPDX-License-Identifier: ISC

`default_nettype none
`timescale 1ns / 1ps

`include "../src/error_counter.v"

// ============================================================================

module tb;

// ============================================================================

reg CLK;
initial CLK <= 1'b0;
always #0.5 CLK <= !CLK;

reg [3:0] rst_sr;
initial rst_sr <= 4'hF;
always @(posedge CLK) rst_sr <= rst_sr >> 1;
wire RST;
assign RST = rst_sr[0];

// ============================================================================

initial begin
    $dumpfile("waveforms.vcd");
    $dumpvars;
end

integer cycle_cnt;
initial cycle_cnt <= 0;

always @(posedge CLK)
    if (!RST) cycle_cnt <= cycle_cnt + 1;

always @(posedge CLK)
    if (!RST && cycle_cnt >= 150)
        $finish;

// ============================================================================

//re i_stb = (cycle_cnt == 10);
//re [32*2-1:0] i_dat = 64'h01234567_ABCD4321;

wire o_stb;
wire [4*8-1:0] o_dat;

error_counter #
(
.COUNT_WIDTH    (8),
.DELAY_TAPS     (4)
)
dut
(
.CLK    (CLK),
.RST    (RST),

.O_STB  (o_stb),
.O_DAT  (o_dat)
);

always @(posedge CLK)
    if (o_stb)
        $display("%X", o_dat);

endmodule

