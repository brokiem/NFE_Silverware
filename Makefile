
SDIR = .
VPATH = $(SDIR)/Silverware/src:$(SDIR)/Utilities:$(SDIR)/Libraries/STM32F0xx_StdPeriph_Driver/src:$(SDIR)/Libraries/CMSIS/Device/ST/STM32F0xx/Source/Templates/arm
SRC_C = $(wildcard $(SDIR)/Silverware/src/*.c) \
	$(wildcard $(SDIR)/Utilities/*.c) \
	$(wildcard $(SDIR)/Libraries/STM32F0xx_StdPeriph_Driver/src/*.c)
SRC_CXX = $(wildcard $(SDIR)/Silverware/src/*.cpp)
SRC_S = $(SDIR)/Libraries/CMSIS/Device/ST/STM32F0xx/Source/Templates/arm/startup_stm32f031.s

INCLUDES := -I$(SDIR)/Silverware/src -I$(SDIR)/Libraries/CMSIS/Device/ST/STM32F0xx/Include -I$(SDIR)/Libraries/CMSIS/Include -I$(SDIR)/Utilities -I$(SDIR)/Libraries/STM32F0xx_StdPeriph_Driver/inc

CC = armclang
CXX = armclang
AS = armasm
LD = armlink
FROMELF = fromelf

TARGET_FLAGS = --target=arm-arm-none-eabi -mcpu=cortex-m0 -mthumb
DEFS = -D__MICROLIB -DUSE_STDPERIPH_DRIVER -DSTM32F031

CFLAGS   := $(TARGET_FLAGS) $(DEFS) -g -O2 -ffast-math -std=c99 $(INCLUDES)
CXXFLAGS := $(TARGET_FLAGS) $(DEFS) -g -O2 -ffast-math -std=c++11 $(INCLUDES)
ASMFLAGS := --cpu Cortex-M0 -g --apcs=interwork --pd "__MICROLIB SETA 1" --xref
LDFLAGS  := --cpu Cortex-M0 --library_type=microlib --ro-base 0x08000000 --entry 0x08000000 --rw-base 0x20000000 --entry Reset_Handler --first __Vectors --strict --info summarysizes

SRCS     := $(SRC_C) $(SRC_CXX) $(SRC_S)
ODIR     = $(SDIR)/obj

OBJS 	 = $(addprefix $(ODIR)/, $(notdir $(SRC_C:.c=.o) $(SRC_S:.s=.o) $(SRC_CXX:.cpp=.o)))

.PHONY: default all clean
default: silverware.hex
all: silverware.hex

$(VERBOSE).SILENT:

$(OBJS): | $(ODIR)

$(ODIR):
	@mkdir -p $@

$(ODIR)/%.o: %.cpp
	@echo " + Compiling '$(notdir $<)'"
	$(CXX) $(CXXFLAGS) -c -o $@ $<

$(ODIR)/%.o: %.c
	@echo " + Compiling '$(notdir $<)'"
	$(CC) $(CFLAGS) -c -o $@ $<

$(ODIR)/%.o: %.s
	@echo " + Assembling '$(notdir $<)'"
	$(AS) $(ASMFLAGS) -o $@ $<

silverware.hex: silverware.axf
	$(FROMELF) $< --i32combined --output $@

silverware.axf: $(OBJS)
	$(LD) $(LDFLAGS) $(OBJS) -o $@

clean:
	rm -Rf $(ODIR) silverware.axf silverware.hex
