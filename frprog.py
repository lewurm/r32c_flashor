#!/usr/bin/env python
"""
This file realize a simple programmer, which communicates with our "pkernel"
firmware.
"""
import sys, time
from SerialPort_linux import SerialPort, SerialPortException

# baudrate used for initialization
INIT_BAUDRATE = 9600
# baudrate used for communication with the internal bootloader after init
BOOTLOADER_BAUDRATE = 38400
# baudrate used for communication with the pkernel program that does the
# flashing eventually
KERNEL_BAUDRATE = 115200
# constant for output
SPLIT = 30

# contains the last received checksum from a READ, WRITE or CHECKSUM command
lastchecksum = 0

class FlashSequence(object):
	def __init__(self, address, data):
		self.address = address
		self.data = data

def sendbyte(byte):
	"""
	send a byte to the TTY-device
	"""
	tty.write(chr(byte))

def sendword(word):
	"""
	send a word to the TTY-device
	"""
	sendbyte(word & 0xFF)
	sendbyte((word >> 8) & 0xFF)

def senddword(dword):
	"""
	send a dword to the TTY-device
	"""
	sendbyte(dword & 0xFF)
	sendbyte((dword >> 8) & 0xFF)
	sendbyte((dword >> 16) & 0xFF)
	sendbyte((dword >> 24) & 0xFF)

def recvbyte():
	"""
	receive a byte from the TTY-device
	"""
	return ord(tty.read())

def recvchecksum():
	"""
	receive checksum from the bootROM firmware
	"""
	global lastchecksum
	lastchecksum = recvbyte()
	lastchecksum |= (recvbyte() << 8)

def bootromread(address, size):
	"""
	send a READ-command to the bootROM-firmware
	"""
	# send READ command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x02)
	if (recvbyte() != 0x82):
		raise Exception
	# tell desired address and size
	senddword(address)
	sendword(size)
	# get binary stream of data
	data = []
	for _ in range(0, size):
		data.append(recvbyte())
	# get checksum
	recvchecksum()
	return data

def bootromwrite(address, size, data):
	"""
	send a WRITE-command to the bootROM-firmware
	"""
	# send WRITE command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x03)
	if (recvbyte() != 0x83):
		raise Exception
	# tell desired address and size
	senddword(address)
	sendword(size)
	# write binary stream of data
	for i in range(0, size):
		sendbyte(data[i])
	# get checksum
	recvchecksum()

def bootromcall(address):
	"""
	send a CALL-command to the bootROM-firmware
	"""
	# send CALL command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x04)
	if (recvbyte() != 0x84):
		raise Exception
	# tell desired address
	senddword(address)
	# wait for return parameter - not needed here!
	#return recvbyte()

# TODO: test this function!
def bootromchecksum():
	"""
	send a CHECKSUM-command to the bootROM-firmware
	"""
	# call CHECKSUM command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x05)
	if (recvbyte() != 0x84):
		raise Exception
	# get checksum
	recvchecksum()

def bootrombaudrate(baudrate):
	"""
	send a BAUDRAME-command to the bootROM-firmware
	"""
	# send BAUDRATE command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x06)
	if (recvbyte() != 0x86):
		raise Exception
	# send desired baudrate
	senddword(baudrate)

def pkernchiperase():
	"""
	send a CHIPERASE-command to the pkernel-firmware
	"""
	sendbyte(0x15)
	if (recvbyte() != 0x45):
		raise Exception
	# wait till completion...
	if (recvbyte() != 0x23):
		raise Exception

def pkernerase(address, size):
	"""
	send a ERASE-command to the pkernel-firmware
	"""
	sendbyte(0x12)
	if (recvbyte() != 0x11):
		raise Exception
	senddword(address)
	sendword(size)
	if (recvbyte() != 0x18):
		raise Exception

def pkernwrite(address, size, data):
	"""
	send a WRITE-command to the pkernel-firmware
	"""
	# send WRITE command
	sendbyte(0x13)
	if (recvbyte() != 0x37):
		raise Exception
	# tell desired address and size
	senddword(address)
	sendword(size)

	# write binary stream of data
	for i in range(0, size):
		sendbyte(data[i])

	if (recvbyte() != 0x28):
		raise Exception

def readmhxfile(filename): # desired mhx filename
	"""
	proceeds a MHX-File
	"""
	filep = open(filename, "r")
	retval = [] # returns a list of FlashSequence objects
	linecount = 0
	for line in filep:
		linecount += 1
		# get rid of newline characters
		line = line.strip()

		# we're only interested in S2 (data sequence with 3 address bytes)
		# records by now
		if line[0:2] == "S2":
			byte_count = int(line[2:4], 16)
			# just to get sure, check if byte count field is valid
			if (len(line)-4) != (byte_count*2):
				print sys.argv[0] + ": Warning - inavlid byte count field in " + \
					sys.argv[1] + ":" + str(linecount) + ", skipping line!"
				continue

			# address and checksum bytes are not needed
			byte_count -= 4
			address = int(line[4:10], 16)
			datastr = line[10:10+byte_count*2]

			# convert data hex-byte-string to real byte data list
			data = []
			for i in range(0, len(datastr)/2):
				data.append(int(datastr[2*i:2*i+2], 16))

			# add flash sequence to our list
			retval.append(FlashSequence(address, data))
	filep.close()
	return retval

def usage(execf):
	"""
	print usage of frprog
	"""
	print "Usage: " + execf + " <target mhx-file> [-d DEVICE]"

def main(argv=None):
	"""
	main function of frprog
	"""
	# check command line arguments
	if argv is None:
		argv = sys.argv

	if len(argv) == 2 and (argv[1] == "-v" or argv[1] == "--version"):
		print "Version: %VERSION%"
		return 0

	if len(argv) != 2 and len(argv) != 4:
		usage(argv[0])
		return 1

	# standard serial device to communicate with
	device = "/dev/ttyUSB0"

	# overrule standard device if provided with -d
	if len(argv) == 4:
		if argv[2] == "-d":
			device = argv[3]
		else:
			usage(argv[0])
			return 1

	# read in data from mhx-files before starting
	try:
		try:
			bootloaderseqs = readmhxfile("pkernel/pkernel.mhx")
		except IOError as _:
			bootloaderseqs = readmhxfile("%PREFIX%/share/frprog/pkernel.mhx")
		pkernelseqs = readmhxfile(argv[1])
	except IOError as error:
		print argv[0] + ": Error - couldn't open file " + error.filename + "!"
		return 1

	print "Initializing serial port..."
	global tty
	tty = SerialPort(device, 100, INIT_BAUDRATE)

	print "Please press RESET on your board..."

	while True:
		tty.write('V')
		tty.flush()
		try:
			if tty.read() == 'F':
				break
		except SerialPortException:
			# timeout happened, who cares ;-)
			pass

	# save time at this point for evaluating the duration at the end
	starttime = time.time()

	print "OK, trying to set baudrate..."
	# set baudrate
	try:
		bootrombaudrate(BOOTLOADER_BAUDRATE)
	except SerialPortException:
		print "timeout exception: try again ->"
		bootrombaudrate(BOOTLOADER_BAUDRATE)
	# just to get sure that the bootloader is really running in new baudrate mode!
	time.sleep(0.1)
	del tty
	tty = SerialPort(device, 100, BOOTLOADER_BAUDRATE)

	sdots = SPLIT
	print "Transfering pkernel program to IRAM",
	# let the fun begin!
	for seq in bootloaderseqs:
		if(seq.address <= 0x40000):
			addr = seq.address
		else:
			continue
		#print "RAMing", len(seq.data), "bytes at address", hex(addr)
		bootromwrite(addr, len(seq.data), seq.data)
		tty.flush()

		sdots = sdots - 1
		if sdots == 0:
			sys.stdout.write(".")
			sys.stdout.flush()
			sdots = SPLIT
	print

	# execute our pkernel finally and set pkernel conform baudrate
	bootromcall(0x30000)
	time.sleep(0.1) # just to get sure that the pkernel is really running!
	del tty
	tty = SerialPort(device, None, KERNEL_BAUDRATE)

	print "Performing ChipErase..."
	pkernchiperase()

	sdots = SPLIT
	print "Flashing",
	for seq in pkernelseqs:
		# skip seqs only consisting of 0xffs
		seqset = list(set(seq.data))
		if len(seqset) == 1 and seqset[0] == 0xff:
			continue
		#print "Flashing", len(seq.data), "bytes at address", hex(seq.address)
		pkernwrite(seq.address, len(seq.data), seq.data)
		tty.flush()

		sdots = sdots - 1
		if sdots == 0:
			sys.stdout.write(".")
			sys.stdout.flush()
			sdots = SPLIT
	print

	duration = time.time() - starttime
	print "Procedure complete, took", round(duration, 2), "seconds."

	sendbyte(0x97) # exit and restart
	print "Program was started. Have fun!"


if __name__ == '__main__':
	sys.exit(main())
